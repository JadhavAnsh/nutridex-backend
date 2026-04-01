from rest_framework.decorators import api_view, permission_classes, APIView, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .serializers import *
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.views.decorators.csrf import csrf_exempt
from .models import *
from django.http import JsonResponse
from models.ingrediants_ocr import IngredientExtractor
import logging
import joblib
import pickle
import pandas as pd

logger = logging.getLogger(__name__)

def load_pickle_file(file_path):
    """Helper function to load pickle files with multiple methods"""
    logger.info(f"Attempting to load file: {file_path}")
    
    # Try joblib first
    try:
        return joblib.load(file_path)
    except Exception as e:
        logger.warning(f"Joblib load failed: {str(e)}")
    
    # Try pickle with different protocols
    for protocol in range(5):
        try:
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning(f"Pickle load failed with protocol {protocol}: {str(e)}")
            continue
            
    raise ValueError(f"Failed to load file: {file_path}")

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import login
import json

@api_view(["POST"])
@csrf_exempt
@permission_classes([AllowAny])
def register(request):
    if request.method == "POST":
        try:
            # Add explicit debug logging
            logger.info(f"Request method: {request.method}")
            logger.info(f"Raw body: {request.body}")
            logger.info(f"Content type: {request.content_type}")
            
            # Parse data based on content type
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.data
                
            logger.info(f"Parsed data: {data}")
            
            full_name = data.get("full_name")
            email = data.get("email")
            password = data.get("password")

            logger.info(f"Registration attempt - Email: {email}, Full name: {full_name}")

            # Validate email
            try:
                validate_email(email)
            except ValidationError:
                logger.warning(f"Invalid email: {email}")
                return JsonResponse({"error": "Invalid email address"}, status=400)

            # Check if user already exists
            if User.objects.filter(email=email).exists():
                logger.warning(f"Email already registered: {email}")
                return JsonResponse({"error": "Email already registered"}, status=400)

            # Create user
            try:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    full_name=full_name
                )
                logger.info(f"User created successfully: {email}")
            except Exception as user_error:
                logger.error(f"Error creating user: {str(user_error)}")
                return JsonResponse({"error": f"Error creating user: {str(user_error)}"}, status=500)

            # Log the user in
            login(request, user)
            
            # Generate access token
            refresh = RefreshToken.for_user(user)
            
            response_data = {
                "message": "Registration successful",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "email": user.email,
                    "full_name": user.full_name
                }
            }
            
            logger.info(f"Registration successful for: {email}")
            return JsonResponse(response_data, status=201)
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

# Login View
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
import json

@api_view(["POST"])
@csrf_exempt
@permission_classes([AllowAny])
def login_view(request):    
    if request.method == "POST":
        try:
            # Debugging: Log the raw request body and content type
            logger.info(f"Login attempt - Request body: {request.body}")
            logger.info(f"Login attempt - Content type: {request.content_type}")
            
            # Parse JSON or form data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.data
            
            logger.info(f"Login attempt - Parsed data: {data}")
            
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                logger.warning("Login attempt - Missing email or password")
                return JsonResponse(
                    {"error": "Email and password are required."},
                    status=400
                )
            
            logger.info(f"Login attempt - Email: {email}")
            
            # Manually authenticate user instead of using authenticate()
            try:
                user = User.objects.get(email=email)
                if not user.check_password(password):
                    logger.warning(f"Login attempt - Invalid password for: {email}")
                    return JsonResponse(
                        {"error": "Invalid credentials. Please check your email and password."},
                        status=401
                    )
            except User.DoesNotExist:
                logger.warning(f"Login attempt - User not found: {email}")
                return JsonResponse(
                    {"error": "Invalid credentials. Please check your email and password."},
                    status=401
                )
            
            # User is authenticated, log them in
            login(request, user)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            response_data = {
                "message": "Login successful",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "unique_id": str(user.unique_id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "weight": user.weight,
                    "height": user.height,
                    "bmi": user.bmi,
                    "conditions": user.conditions
                }
            }
            
            logger.info(f"Login successful for: {email}")
            return JsonResponse(response_data, status=200)
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            return JsonResponse(
                {"error": "An unexpected error occurred. Please try again later."},
                status=500
            )
    
    return JsonResponse(
        {"error": "Method not allowed"},
        status=405
    )
    
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_onboarding(request):
    try:
        user = request.user
        data = request.data
        
        user.weight = data.get('weight', user.weight)
        user.height = data.get('height', user.height)
        user.bmi = data.get('bmi', user.bmi)
        user.conditions = data.get('conditions', user.conditions)
        
        user.save()
        
        return Response({
            "message": "Onboarding data updated successfully",
            "user": {
                "unique_id": str(user.unique_id),
                "email": user.email,
                "full_name": user.full_name,
                "weight": user.weight,
                "height": user.height,
                "bmi": user.bmi,
                "conditions": user.conditions
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error updating onboarding data: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile_view(request):
    try:
        try:
            userprofile = User.objects.get(unique_id=request.user.unique_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User Profile does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserSerializer(userprofile)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response("No Profile Found", status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# @parser_classes([MultiPartParser, FormParser])
# def extract_ingredients_api(request):
#     """API to extract ingredients from an uploaded image and save results to the database."""
    
#     if 'image' not in request.FILES:
#         return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)
    
#     try:
#         image_file = request.FILES['image']
        
#         # Save initial OCR entry
#         ocr_result = OCRResult.objects.create(image=image_file, extracted_data={})
        
#         # Extractor instance
#         extractor = IngredientExtractor()
        
#         # Extract text and ingredients
#         image_path = ocr_result.image.path
#         ingredients_list = extractor.extract_text(image_path)
        
#         result = {
#             "success": True,
#             "ingredients": ingredients_list
#         }

#         # Store the extracted data
#         ocr_result.extracted_data = result["ingredients"]
#         ocr_result.save()
        
#         return JsonResponse(result)
    
#     except Exception as e:
#         return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
# from django.http import JsonResponse
# from rest_framework.decorators import api_view, permission_classes, parser_classes
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.parsers import MultiPartParser, FormParser
# from .models import NutritionResult
# from django.conf import settings
# import os

# from models.nutrition_fact_ocr import FoodLabelOCR  
# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# @parser_classes([MultiPartParser, FormParser])
# def extract_nutrition_api(request):
#     """API view to extract nutrition details from an uploaded food label image"""

#     if 'image' not in request.FILES:
#         return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)

#     try:
#         # Get the uploaded image
#         image_file = request.FILES['image']
        
#         # Save image inside MEDIA_ROOT
#         media_path = os.path.join(settings.MEDIA_ROOT, "uploads")
#         os.makedirs(media_path, exist_ok=True)  # Ensure directory exists
        
#         image_path = os.path.join(media_path, image_file.name)

#         # Save file properly
#         with open(image_path, 'wb') as f:
#             for chunk in image_file.chunks():
#                 f.write(chunk)

#         # Initialize the OCR processor
#         ocr_processor = FoodLabelOCR(use_gpu=False)

#         # Process the image
#         nutrition_result, extracted_text = ocr_processor.process_image(image_path, save_to_db=True)

#         # Delete image after processing
#         if os.path.exists(image_path):
#             os.remove(image_path)

#         # If processing failed
#         if not nutrition_result:
#             return JsonResponse({'success': False, 'error': 'Failed to extract nutrition information'}, status=500)

#         nutrition_data = {
#             "id": nutrition_result.id,
#             "image_name": nutrition_result.image_name,
#             "processed_at": nutrition_result.processed_at.strftime('%Y-%m-%d %H:%M:%S'),
#             "calories": nutrition_result.calories,
#             "protein": nutrition_result.protein,
#             "fats": nutrition_result.fats,
#             "carbohydrates": nutrition_result.carbohydrates,
#             "sugar": nutrition_result.sugar,
#             "sodium": nutrition_result.sodium,
#             "fiber": nutrition_result.fiber,
#             "serving_size": nutrition_result.serving_size,
#             "serving_size_unit": nutrition_result.serving_size_unit,
#         }

#         return JsonResponse({
#             'success': True,
#             'nutrition_info': nutrition_data
#         })

#     except Exception as e:
#         error_msg = f"API error: {str(e)}"
#         return JsonResponse({'success': False, 'error': error_msg}, status=500)

import json
import google.generativeai as genai
from django.conf import settings
from django.http import JsonResponse

def generate_analysis_summary(ingredients_list, nutrition_data, ingredients_score, nutrition_score, total_score):
    """
    Generate an analysis summary using Gemini AI based on ingredients list, 
    nutrition data, and scoring from our models.
    
    Args:
        ingredients_list: List of ingredients extracted
        nutrition_data: Dictionary of nutrition values
        ingredients_score: Score from ingredients model
        nutrition_score: Score from nutrition model
        total_score: Overall calculated score
        
    Returns:
        str: An analysis summary explaining the score and health implications
    """
    try :
        # Configure Gemini AI
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Prepare data for the prompt
        ingredients_text = ", ".join(ingredients_list) if isinstance(ingredients_list, list) else str(ingredients_list)
        nutrition_text = json.dumps(nutrition_data, indent=2)
        
        # Create a categorization based on total score
        if total_score >= 8:
            category = "excellent"
        elif total_score >= 6:
            category = "good"
        elif total_score >= 4:
            category = "moderate"
        else:
            category = "poor"
        
        # Create the prompt for Gemini AI
        prompt = f"""
        As a nutritional expert, analyze the following food product based on its ingredients and nutrition facts.
        
        Ingredients: {ingredients_text}
        
        Nutrition Facts: {nutrition_text}
        
        Model Scores:
        - Ingredients Quality Score: {ingredients_score:.2f}/10
        - Nutritional Value Score: {nutrition_score:.2f}/10
        - Overall Health Score: {total_score:.2f}/10
        - General Category: {category}
        
        Generate a 2-3 sentence analysis summary that explains:
        1. Why this product received its score
        2. Key concerns or benefits from ingredients
        3. A brief recommendation based on the nutritional profile
        
        Keep the summary concise, factual, and actionable.
        """
        
        # Generate response from Gemini
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # Ensure we have a valid summary
        if not summary:
            return "Unable to generate analysis. This product received a {category} score of {total_score:.1f}/10."
            
        return summary
        
    except Exception as e:
        logger.error(f"Error generating analysis summary: {str(e)}")
        return f"This product received a {category} health score of {total_score:.1f}/10."
    

from django.http import JsonResponse
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import OCRResult, NutritionResult, History
import os
import pickle
import sys
import numpy as np
import importlib.util

from models.ingrediants_ocr import IngredientExtractor
from models.nutrition_fact_ocr import FoodLabelOCR

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def result_api(request):
    """
    API that processes ingredients and nutrition data directly from images
    through ML models and saves results to history.
    """
    try:
        if 'ingredients_image' not in request.FILES or 'nutrition_image' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Both ingredients_image and nutrition_image are required'
            }, status=400)

        # Extract ingredients using OCR
        try:
            ingredients_image = request.FILES['ingredients_image']
            
            # Ensure upload directory exists
            ocr_upload_path = os.path.join(settings.MEDIA_ROOT, "ocr_uploads")
            os.makedirs(ocr_upload_path, exist_ok=True)
            
            # Save ingredients image
            ocr_result = OCRResult.objects.create(image=ingredients_image, extracted_data={})
            logger.info(f"Ingredients image saved to: {ocr_result.image.path}")
            
            extractor = IngredientExtractor()
            ingredients_list = extractor.extract_text(ocr_result.image.path)
            
            if not ingredients_list:
                ingredients_list = ["No ingredients detected"]
                
            ocr_result.extracted_data = ingredients_list
            ocr_result.save()
            
        except Exception as e:
            logger.error(f"Ingredients extraction error: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': f'Ingredients error: {str(e)}'}, status=500)

        # Extract nutrition using OCR
        try:
            nutrition_image = request.FILES['nutrition_image']
            
            # Ensure upload directory exists
            nutrition_upload_path = os.path.join(settings.MEDIA_ROOT, "nutrition_uploads")
            os.makedirs(nutrition_upload_path, exist_ok=True)
            
            # Save nutrition image file
            nutrition_path = os.path.join(nutrition_upload_path, nutrition_image.name)
            with open(nutrition_path, 'wb') as f:
                for chunk in nutrition_image.chunks():
                    f.write(chunk)

            ocr_processor = FoodLabelOCR(use_gpu=False)
            nutrition_result, _ = ocr_processor.process_image(nutrition_path, save_to_db=True)
            
            # Only remove if processing succeeded or failed gracefully
            if os.path.exists(nutrition_path):
                try: os.remove(nutrition_path)
                except: pass

            if not nutrition_result:
                return JsonResponse({'success': False, 'error': 'Failed to extract nutrition information'}, status=500)
        except Exception as e:
            logger.error(f"Nutrition extraction error: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': f'Nutrition error: {str(e)}'}, status=500)

        # Load ML models
        try:
            BASE_PATH = r"E:\backend\backend\ml_models"
            vectorizer = load_pickle_file(os.path.join(BASE_PATH, 'tfidf_vectorizer.pkl'))
            ingredients_model = load_pickle_file(os.path.join(BASE_PATH, 'random_forest_model.pkl'))
            nutrition_model = load_pickle_file(os.path.join(BASE_PATH, 'chirag_patil.pkl'))
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Model loading error: {str(e)}\nAvailable files: {os.listdir(BASE_PATH)}'
            }, status=500)

        # Process ingredients
        try:
            # Convert ingredients list to a single string
            ingredients_text = " ".join(str(ingredient) for ingredient in ingredients_list) if ingredients_list else ""
            logger.info(f"Processing ingredients: {ingredients_text[:100]}...")  # Log first 100 chars
            
            # Vectorize as a single string
            ingredients_vector = vectorizer.transform([ingredients_text])
            ingredients_score = (float(ingredients_model.predict(ingredients_vector)[0])*10)  # Multiply by 10
            
            logger.info(f"Ingredients score: {ingredients_score}")
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Ingredients processing error: {str(e)}'
            }, status=500)

        # Process nutrition
        try:
            # Prepare nutrition features in the format expected by chirag_patil.pkl model
            nutrition_data = {
                "Calories": float(nutrition_result.calories or 0),
                "Protein (g)": float(nutrition_result.protein or 0),
                "Fats (g)": float(nutrition_result.fats or 0),
                "Carbohydrates (g)": float(nutrition_result.carbohydrates or 0),
                "Sugars (g)": float(nutrition_result.sugar or 0),
                "Sodium (mg)": float(nutrition_result.sodium or 0),
                "Saturated Fat (g)": float(nutrition_result.saturated_fat_100g or 0),
                "Trans Fat (g)": float(nutrition_result.trans_fat_100g or 0),
                "Cholesterol (mg)": float(nutrition_result.cholesterol_100g or 0)
            }
            
            # Log the data being sent to model
            logger.info(f"Nutrition data for model: {nutrition_data}")
            
            # Convert to DataFrame as expected by the model
            nutrition_df = pd.DataFrame([nutrition_data])
            
            # Make prediction
            prediction = nutrition_model.predict(nutrition_df)
            
            # Extract the nutrition score from the prediction
            if isinstance(prediction, np.ndarray) and prediction.size > 0:
                if len(prediction[0]) > 1:  # If prediction contains [health_class, nutrition_score]
                    health_class, nutrition_score = prediction[0]
                    nutrition_score = float(nutrition_score)
                else:  # If prediction is just the score
                    nutrition_score = float(prediction[0])
            else:
                nutrition_score = 0.0
                
            logger.info(f"Nutrition score: {nutrition_score}")
            
        except Exception as e:
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            logger.error(f"Model type: {type(nutrition_model).__name__}")
            return JsonResponse({
                'success': False,
                'error': f'Nutrition processing error: {str(e)}'
            }, status=500)

        # Calculate total score
        total_score = ingredients_score + nutrition_score / 2  # Adjust weight as needed
        
        # Prepare data structures for storage
        nutrition_data = {
            "calories": nutrition_result.calories,
            "protein": nutrition_result.protein,
            "fats": nutrition_result.fats,
            "carbohydrates": nutrition_result.carbohydrates,
            "sugar": nutrition_result.sugar,
            "sodium": nutrition_result.sodium,
            "saturated_fat": nutrition_result.saturated_fat_100g,
            "trans_fat": nutrition_result.trans_fat_100g,
            "cholesterol": nutrition_result.cholesterol_100g,
        }
        
        ingredients_data = {
            "raw_data": ingredients_list
        }

        # Save to history with all structured data
        try:
            history = History.objects.create(
                user=request.user,
                ingredients_result=ingredients_score,
                nutrition_result=nutrition_score,
                total_result=total_score,
                nutrition_data=nutrition_data,
                ingredients_data=ingredients_data
            )
            history_id = history.id
        except Exception as history_error:
            logger.error(f"Failed to save to history: {str(history_error)}")
            history_id = None

        # Format data for response
        formatted_nutrition_data = {
            "Calories": nutrition_result.calories,
            "Protein (g)": nutrition_result.protein,
            "Fats (g)": nutrition_result.fats,
            "Carbohydrates (g)": nutrition_result.carbohydrates,
            "Sugars (g)": nutrition_result.sugar,
            "Sodium (mg)": nutrition_result.sodium,
            "Saturated Fat (g)": nutrition_result.saturated_fat_100g,
            "Trans Fat (g)": nutrition_result.trans_fat_100g,
            "Cholesterol (mg)": nutrition_result.cholesterol_100g,
        }
        
        try:
        # Generate analysis summary
            analysis_summary = generate_analysis_summary(
            ingredients_list=ingredients_list,
            nutrition_data=formatted_nutrition_data,
            ingredients_score=ingredients_score,
            nutrition_score=nutrition_score,
            total_score=total_score
        )   
            # Update history object with summary
            if history_id:
                history = History.objects.get(id=history_id)
                history.analysis_summary = analysis_summary
                history.save()
        except Exception as summary_error:
            logger.error(f"Failed to generate or save analysis summary: {str(summary_error)}")
            analysis_summary = f"This product received a score of {total_score:.1f}/10."
        
# Modify the return statement to include the summary
        return JsonResponse({
            'success': True,
            'history_id': history_id,
            'ingredients': {
                'raw_data': ingredients_list,
                'score': ingredients_score  # Add ingredients score
            },
            'nutrition': {
                'data': formatted_nutrition_data,
                'score': nutrition_score  # Add nutrition score
            },
            'total_score': total_score,
        'analysis_summary': analysis_summary,  # Add this line
        'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_history(request):
    """
    API to fetch the history of results for the authenticated user.
    
    Returns:
        A list of history records with scores and detailed data.
        Can be filtered by date range using query parameters 'start_date' and 'end_date'.
    """
    try:
        # Get query parameters for filtering
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = request.query_params.get('limit', 10)  # Default to 10 records
        
        # Query the user's history, ordered by most recent first
        history_query = History.objects.filter(user=request.user).order_by('-created_at')
        
        # Apply date filters if provided
        if start_date:
            history_query = history_query.filter(created_at__gte=start_date)
        if end_date:
            history_query = history_query.filter(created_at__lte=end_date)
            
        # Apply limit
        try:
            limit = int(limit)
        except ValueError:
            limit = 10
        history_query = history_query[:limit]
        
        # Format the history data
        history_data = []
        for record in history_query:
            history_data.append({
                'id': record.id,
                'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'scores': {
                    'ingredients': record.ingredients_result,
                    'nutrition': record.nutrition_result,
                    'total': record.total_result
                },
                'nutrition_data': record.nutrition_data,
                'ingredients_data': record.ingredients_data,
                'analysis_summary': record.analysis_summary  # Add this line
            })
        
        return JsonResponse({
            'success': True,
            'count': len(history_data),
            'history': history_data
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error fetching history: {str(e)}'
        }, status=500)
    

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manual_entry_api(request):
    """
    API that processes manually entered ingredients and nutrition data
    and saves results to history, similar to result_api but without image processing.
    """
    try:
        # Check if required data is provided
        if 'ingredients_text' not in request.data or 'nutrition_data' not in request.data:
            return JsonResponse({
                'success': False,
                'error': 'Both ingredients_text and nutrition_data are required'
            }, status=400)

        ingredients_text = request.data['ingredients_text']
        nutrition_input = request.data['nutrition_data']
        
        # Process ingredients
        try:
            # Convert ingredients text to list (assuming comma-separated format)
            ingredients_list = [ingredient.strip() for ingredient in ingredients_text.split(',')]
            
            # Load ML models
            BASE_PATH = r"E:\backend\backend\ml_models"
            vectorizer = load_pickle_file(os.path.join(BASE_PATH, 'tfidf_vectorizer.pkl'))
            ingredients_model = load_pickle_file(os.path.join(BASE_PATH, 'random_forest_model.pkl'))
            nutrition_model = load_pickle_file(os.path.join(BASE_PATH, 'chirag_patil.pkl'))
            
            # Vectorize ingredients text
            ingredients_vector = vectorizer.transform([ingredients_text])
            ingredients_score = (float(ingredients_model.predict(ingredients_vector)[0])*10)
            
            logger.info(f"Ingredients score: {ingredients_score}")
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Ingredients processing error: {str(e)}'
            }, status=500)

        # Process nutrition
        try:
            # Parse nutrition input data
            nutrition_data = {
                "Calories": float(nutrition_input.get('calories', 0)),
                "Protein (g)": float(nutrition_input.get('protein', 0)),
                "Fats (g)": float(nutrition_input.get('fats', 0)),
                "Carbohydrates (g)": float(nutrition_input.get('carbohydrates', 0)),
                "Sugars (g)": float(nutrition_input.get('sugar', 0)),
                "Sodium (mg)": float(nutrition_input.get('sodium', 0)),
                "Saturated Fat (g)": float(nutrition_input.get('saturated_fat', 0)),
                "Trans Fat (g)": float(nutrition_input.get('trans_fat', 0)),
                "Cholesterol (mg)": float(nutrition_input.get('cholesterol', 0))
            }
            
            # Log the data being sent to model
            logger.info(f"Nutrition data for model: {nutrition_data}")
            
            # Convert to DataFrame as expected by the model
            nutrition_df = pd.DataFrame([nutrition_data])
            
            # Make prediction
            prediction = nutrition_model.predict(nutrition_df)
            
            # Extract the nutrition score from the prediction
            if isinstance(prediction, np.ndarray) and prediction.size > 0:
                if len(prediction[0]) > 1:  # If prediction contains [health_class, nutrition_score]
                    health_class, nutrition_score = prediction[0]
                    nutrition_score = float(nutrition_score)
                else:  # If prediction is just the score
                    nutrition_score = float(prediction[0])
            else:
                nutrition_score = 0.0
                
            logger.info(f"Nutrition score: {nutrition_score}")
            
        except Exception as e:
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception details: {str(e)}")
            logger.error(f"Model type: {type(nutrition_model).__name__}")
            return JsonResponse({
                'success': False,
                'error': f'Nutrition processing error: {str(e)}'
            }, status=500)

        # Calculate total score
        total_score = ingredients_score + nutrition_score / 2  # Adjust weight as needed
        
        # Prepare data structures for storage
        nutrition_data_for_storage = {
            "calories": nutrition_input.get('calories'),
            "protein": nutrition_input.get('protein'),
            "fats": nutrition_input.get('fats'),
            "carbohydrates": nutrition_input.get('carbohydrates'),
            "sugar": nutrition_input.get('sugar'),
            "sodium": nutrition_input.get('sodium'),
            "saturated_fat": nutrition_input.get('saturated_fat'),
            "trans_fat": nutrition_input.get('trans_fat'),
            "cholesterol": nutrition_input.get('cholesterol'),
        }
        
        ingredients_data = {
            "raw_data": ingredients_list
        }

        # Save to history with all structured data
        try:
            history = History.objects.create(
                user=request.user,
                ingredients_result=ingredients_score,
                nutrition_result=nutrition_score,
                total_result=total_score,
                nutrition_data=nutrition_data_for_storage,
                ingredients_data=ingredients_data,
            )
            history_id = history.id
            
            # Generate and update analysis summary
            analysis_summary = generate_analysis_summary(
                ingredients_list=ingredients_list,
                nutrition_data=nutrition_data_for_storage,
                ingredients_score=ingredients_score,
                nutrition_score=nutrition_score,
                total_score=total_score
            )
            
            # Update the history record with the summary
            history.analysis_summary = analysis_summary
            history.save()
            
            logger.info(f"Successfully created history entry with ID: {history_id}")
            
        except Exception as history_error:
            logger.error(f"Failed to save to history: {str(history_error)}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to save results: {str(history_error)}'
            }, status=500)

        # Format data for response
        formatted_nutrition_data = {
            "Calories": nutrition_input.get('calories'),
            "Protein (g)": nutrition_input.get('protein'),
            "Fats (g)": nutrition_input.get('fats'),
            "Carbohydrates (g)": nutrition_input.get('carbohydrates'),
            "Sugars (g)": nutrition_input.get('sugar'),
            "Sodium (mg)": nutrition_input.get('sodium'),
            "Saturated Fat (g)": nutrition_input.get('saturated_fat'),
            "Trans Fat (g)": nutrition_input.get('trans_fat'),
            "Cholesterol (mg)": nutrition_input.get('cholesterol'),
        }

        try:
        # Generate analysis summary
            analysis_summary = generate_analysis_summary(
            ingredients_list=ingredients_list,
            nutrition_data=formatted_nutrition_data,
            ingredients_score=ingredients_score,
            nutrition_score=nutrition_score,
            total_score=total_score
        )       # Update history object with summary
            if history_id:
                history = History.objects.get(id=history_id)
                history.analysis_summary = analysis_summary
                history.save()
        except Exception as summary_error:
            logger.error(f"Failed to generate or save analysis summary: {str(summary_error)}")
            analysis_summary = f"This product received a score of {total_score:.1f}/10."

# Modify the return statement to include the summary
        return JsonResponse({
            'success': True,
            'history_id': history_id,
            'ingredients': {
                'raw_data': ingredients_list,
                'score': ingredients_score  # Add ingredients score
            },
            'nutrition': {
            'data': formatted_nutrition_data,
            'score': nutrition_score  # Add nutrition score
        },
        'total_score': total_score,
        'analysis_summary': analysis_summary,  # Add this line
        'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)

