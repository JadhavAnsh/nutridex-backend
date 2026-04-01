import cv2
import re
import spacy
import logging
import os
import numpy as np  # Add this import
from paddleocr import PaddleOCR
from django.utils import timezone
from Authentication.models import NutritionResult
import google.generativeai as genai
from django.conf import settings
import base64

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FoodLabelOCR:
    """Service for OCR processing of food labels""" 
    
    NUTRITION_PATTERNS = {
        # Updated calories pattern with more variations and flexibility
        'calories': r'(?:calories|energy|cal\.?|calorie content|kcal|nutritional value)[\s:]*(\d+[\.,]?\d*)\s*(?:kcal|cal|kj|calories|$)',
        'protein': r'(?:protein|proteins|prot\.?|proteines?)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'fats': r'(?:total fat|fats?|lipids|fat content|total lipids?)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'carbohydrates': r'(?:carbohydrates?|carbs?|total carbs?|glucides|total carbohydrates?)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'sugar': r'(?:sugars?|total sugars?|of which sugars?)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'sodium': r'(?:sodium|salt|na|salt content)[\s:]*(\d+[\.,]?\d*)\s*(?:mg|g|milligrams?|grams?|$)',
        'saturated_fat_100g': r'(?:saturated fat|saturates|sat\.?\s*fat|saturated)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'trans_fat_100g': r'(?:trans\s*fat|trans-fat|trans\s*fatty acids?)[\s:]*(\d+[\.,]?\d*)\s*(?:g|grams?|gr|$)',
        'cholesterol_100g': r'(?:cholesterol|chol\.?)[\s:]*(\d+[\.,]?\d*)\s*(?:mg|milligrams?|g|$)',
    }
    
    def __init__(self, use_gpu=False):
        """Initialize the OCR service"""
        try:
            self.ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=use_gpu)
            logger.info("PaddleOCR initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {str(e)}")
            raise
            
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("SpaCy model loaded successfully")
        except OSError as e:
            logger.error(f"SpaCy model not found: {str(e)}")
            logger.error("Please install using: python -m spacy download en_core_web_sm")
            raise
        
        # Initialize Gemini AI
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Gemini AI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini AI: {str(e)}")
            self.gemini_model = None
    
    def preprocess_image(self, image):
        """Enhanced image preprocessing pipeline"""
        # Initial grayscale conversion
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Noise reduction
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # Contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(denoised)
        
        # Thresholding with multiple methods
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                      cv2.THRESH_BINARY, 11, 2)
        
        # Combine thresholding results
        combined = cv2.bitwise_and(binary, adaptive)
        
        # Text enhancement
        kernel = np.ones((2,2), np.uint8)
        dilated = cv2.dilate(combined, kernel, iterations=1)
        cleaned = cv2.erode(dilated, kernel, iterations=1)
        
        return cleaned
    
    def extract_nutrition_info(self, text):
        """Extract nutritional information with improved text preprocessing"""
        nutrition_data = {}
        
        # Text preprocessing
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = text.replace(',', '.')  # Handle European decimals
        text = re.sub(r'[^\w\s.:]', ' ', text)  # Remove special chars except dots and colons
        text = re.sub(r'\(.*?\)', '', text)  # Remove parenthetical content
        
        # Debug logging for calories detection
        calories_matches = list(re.finditer(self.NUTRITION_PATTERNS['calories'], text))
        if calories_matches:
            logger.info(f"Found {len(calories_matches)} potential calories matches")
            for idx, match in enumerate(calories_matches):
                logger.info(f"Calories match {idx+1}: {match.group(0)} -> value: {match.group(1)}")
        else:
            logger.warning(f"No calories detected in text. Sample text: {text[:200]}...")
            
            # Try a fallback pattern for calories
            fallback_pattern = r'(\d+)\s*(?:kcal|calories|cal)'
            fallback_match = re.search(fallback_pattern, text)
            if fallback_match:
                logger.info(f"Found calories using fallback pattern: {fallback_match.group(0)}")
                try:
                    nutrition_data['calories'] = float(fallback_match.group(1))
                except (ValueError, IndexError):
                    pass
        
        # Process each nutrient
        for nutrient, pattern in self.NUTRITION_PATTERNS.items():
            matches = list(re.finditer(pattern, text))
            
            if matches:
                values = []
                for match in matches:
                    try:
                        value = float(match.group(1).replace(',', '.'))
                        if 0 <= value <= 1000:  # Sanity check for realistic values
                            values.append(value)
                    except (ValueError, IndexError):
                        continue
                
                if values:
                    # Use median for multiple matches to avoid outliers
                    nutrition_data[nutrient] = round(sorted(values)[len(values)//2], 2)
        
        return nutrition_data
    
    def extract_nutrition_with_gemini(self, extracted_text, image_path=None):
        """Use Gemini AI to directly extract nutrition information from text and image"""
        if not self.gemini_model:
            logger.warning("Gemini AI not available for extraction")
            return self.extract_nutrition_info(extracted_text)  # Fallback to regex
            
        try:
            # Prepare the image if available
            image_parts = []
            if image_path and os.path.isfile(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        image_data = img_file.read()
                        encoded_image = base64.b64encode(image_data).decode('utf-8')
                        image_parts = [
                            {
                                "mime_type": "image/jpeg",
                                "data": encoded_image
                            }
                        ]
                        logger.info("Successfully encoded image for Gemini")
                except Exception as img_error:
                    logger.error(f"Error encoding image: {str(img_error)}")
            
            prompt = f"""
            You are a nutrition fact expert. I have scanned a food product and extracted the following text. 
            Please extract ONLY the nutrition facts data from this text:

            {extracted_text}

            Extract the following nutritional values (use 0 if not found):
            - calories
            - protein (g)
            - fats or total fat (g)
            - carbohydrates or carbs (g)
            - sugar (g)
            - sodium (mg)
            - saturated fat (g)
            - trans fat (g)
            - cholesterol (mg)

            Respond ONLY with a valid JSON object containing these nutrition values as numbers (not strings).
            For example:
            {{
              "calories": 120,
              "protein": 2,
              "fats": 5, 
              "carbohydrates": 20,
              "sugar": 10,
              "sodium": 200,
              "saturated_fat": 1.5,
              "trans_fat": 0,
              "cholesterol": 0
            }}
            """
            
            # Get response from Gemini with or without image
            if image_parts:
                response = self.gemini_model.generate_content(
                    [prompt] + image_parts
                )
            else:
                response = self.gemini_model.generate_content(prompt)
                
            gemini_text = response.text.strip()
            
            # Extract JSON from response
            import json
            
            # Find JSON pattern in the response
            json_match = re.search(r'\{.*\}', gemini_text, re.DOTALL)
            if json_match:
                try:
                    nutrition_data = json.loads(json_match.group(0))
                    
                    # Convert keys to match our expected format
                    result = {}
                    key_mapping = {
                        'calories': 'calories',
                        'protein': 'protein',
                        'fats': 'fats', 
                        'total_fat': 'fats',
                        'carbohydrates': 'carbohydrates',
                        'carbs': 'carbohydrates',
                        'sugar': 'sugar',
                        'sugars': 'sugar',
                        'sodium': 'sodium',
                        'saturated_fat': 'saturated_fat_100g',
                        'trans_fat': 'trans_fat_100g',
                        'cholesterol': 'cholesterol_100g'
                    }
                    
                    # Map the returned keys to our expected keys
                    for key, value in nutrition_data.items():
                        normalized_key = key.lower().replace(' ', '_')
                        if normalized_key in key_mapping:
                            result[key_mapping[normalized_key]] = float(value)
                    
                    # Ensure we have values for all our expected fields
                    for target_key in ['calories', 'protein', 'fats', 'carbohydrates', 'sugar', 
                                      'sodium', 'saturated_fat_100g', 'trans_fat_100g', 'cholesterol_100g']:
                        if target_key not in result:
                            result[target_key] = 0.0
                    
                    logger.info(f"Successfully extracted nutrition data with Gemini: {len(result)} fields")
                    return result
                    
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Could not parse Gemini nutrition response: {str(e)}")
            else:
                logger.warning(f"No JSON found in Gemini nutrition response")
            
            # Fall back to regex extraction if Gemini fails
            return self.extract_nutrition_info(extracted_text)
            
        except Exception as e:
            logger.error(f"Error extracting nutrition with Gemini: {str(e)}")
            return self.extract_nutrition_info(extracted_text)
    
    def validate_with_gemini(self, extracted_text, nutrition_info, image_path=None):
        """Use Gemini AI to validate and fix nutrition information, optionally with image"""
        if not self.gemini_model:
            logger.warning("Gemini AI not available for validation")
            return nutrition_info
            
        try:
            # Create prompt with extracted information
            missing_fields = []
            for field in ['calories', 'protein', 'fats', 'carbohydrates', 'sugar', 'sodium']:
                if field not in nutrition_info or nutrition_info[field] == 0:
                    missing_fields.append(field)
            
            if not missing_fields and not image_path:
                logger.info("No missing fields to validate with Gemini")
                return nutrition_info

            logger.info(f"Validating with Gemini: {missing_fields}")
            
            # Prepare the image if available
            image_parts = []
            if image_path and os.path.isfile(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        image_data = img_file.read()
                        encoded_image = base64.b64encode(image_data).decode('utf-8')
                        image_parts = [
                            {
                                "mime_type": "image/jpeg",
                                "data": encoded_image
                            }
                        ]
                        logger.info("Successfully encoded image for Gemini")
                except Exception as img_error:
                    logger.error(f"Error encoding image: {str(img_error)}")
            
            prompt = f"""
            I have a food nutrition label with the following extracted text:
            
            {extracted_text}
            
            I've extracted some nutrition information, but I'm missing values for: {', '.join(missing_fields) if missing_fields else 'none'}.
            
            Here's what I already extracted:
            {nutrition_info}
            
            Please analyze {"the image and " if image_parts else ""}text to provide the most accurate nutrition information.
            Only respond with a valid JSON object containing the complete nutrition information.
            For example: {{"calories": 120, "protein": 5, "fats": 3, "carbohydrates": 20, "sugar": 2, "sodium": 35}}
            """
            
            # Get response from Gemini with or without image
            if image_parts:
                response = self.gemini_model.generate_content(
                    [prompt] + image_parts
                )
            else:
                response = self.gemini_model.generate_content(prompt)
                
            gemini_text = response.text.strip()
            
            # Extract JSON from response
            import re
            import json
            
            # Find JSON pattern in the response
            json_match = re.search(r'\{.*\}', gemini_text, re.DOTALL)
            if json_match:
                try:
                    gemini_data = json.loads(json_match.group(0))
                    
                    # Update nutrition info with Gemini's suggestions
                    for field, value in gemini_data.items():
                        if field in nutrition_info and (nutrition_info[field] == 0 or field in missing_fields):
                            if isinstance(value, (int, float)) and 0 <= value <= 1000:
                                nutrition_info[field] = value
                                logger.info(f"Updated {field} with Gemini value: {value}")
                    
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse Gemini response as JSON: {gemini_text}")
            else:
                logger.warning(f"No JSON found in Gemini response: {gemini_text}")
            
            return nutrition_info
            
        except Exception as e:
            logger.error(f"Error validating with Gemini: {str(e)}")
            return nutrition_info
    
    def process_image(self, image_path, save_to_db=True):
        """
        Process an image and extract nutritional information
        
        Args:
            image_path: Path to the image file
            save_to_db: Whether to save results to database
            
        Returns:
            tuple: (nutrition_result_object or dict, extracted_text)
        """
        try:
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Failed to read image from {image_path}")
                return None, "Failed to read image"
                
            # Get image dimensions
            height, width = image.shape[:2]
            
            # Process full image and potentially cropped sections
            results = []
            
            # Process full image
            processed_full = self.preprocess_image(image)
            full_result = self.ocr.ocr(processed_full)
            if full_result and isinstance(full_result, list) and len(full_result) > 0 and isinstance(full_result[0], list):
                results.extend([line[1][0] for line in full_result[0] if line and len(line) > 1 and isinstance(line[1], list) and len(line[1]) > 0])
            else:
                logger.warning("No OCR results found for full image.")
            
            # Process bottom half (nutrition facts often at bottom)
            bottom_half = image[height//2:, :]
            processed_bottom = self.preprocess_image(bottom_half)
            bottom_result = self.ocr.ocr(processed_bottom)
            if bottom_result and isinstance(bottom_result, list) and len(bottom_result) > 0 and isinstance(bottom_result[0], list):
                results.extend([line[1][0] for line in bottom_result[0] if line and len(line) > 1 and isinstance(line[1], list) and len(line[1]) > 0])
            else:
                logger.warning("No OCR results found for bottom half of image.")
            
            # Combine and clean text
            text = " ".join(results)
            
            # Try direct Gemini extraction first (with image)
            nutrition_info = self.extract_nutrition_with_gemini(text, image_path)
            
            # Save to database if requested
            if save_to_db and nutrition_info:
                return self.save_to_database(image_path, text, nutrition_info), text
            
            return nutrition_info, text
                
        except Exception as e:
            error_msg = f"Error processing image: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def save_to_database(self, image_path, text, nutrition_info):
        """Save extracted nutrition information to database"""
        try:
            # Create a new NutritionResult object
            result = NutritionResult(
                image_path=image_path,
                image_name=os.path.basename(image_path),
                processed_at=timezone.now()
            )
            
            # Set nutrition values based on extracted info
            for field, value in nutrition_info.items():
                if hasattr(result, field):
                    setattr(result, field, value)
            
            # Save to database
            result.save()
            logger.info(f"Saved nutrition result to database with ID: {result.id}")
            return result
            
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            return None


# Example usage function
def run_ocr_on_image(image_path, use_gpu=False, save_to_db=True):
    """
    Run OCR on an image file and return the results
    
    Args:
        image_path: Path to the image file
        use_gpu: Whether to use GPU for OCR
        save_to_db: Whether to save results to database
        
    Returns:
        tuple: (nutrition_info, extracted_text)
    """
    ocr_service = FoodLabelOCR(use_gpu=use_gpu)
    return ocr_service.process_image(image_path, save_to_db=save_to_db)

# Session settings
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Use database-backed sessions
SESSION_COOKIE_AGE = 3600  # Session duration in seconds (e.g., 3600 seconds = 1 hour)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session active after browser is closed
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session expiration on every request