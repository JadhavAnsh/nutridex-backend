import json
import logging
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .models import History
from .views import AI_ANALYSIS_FALLBACK, generate_ai_analysis, generate_analysis_summary, load_pickle_file
from .openfoodfacts_service import fetch_product_from_barcode
import os
import pandas as pd
import numpy as np
from PIL import Image
from pyzbar.pyzbar import decode

logger = logging.getLogger(__name__)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def barcode_scan_api(request):
    try:
        barcode = request.data.get('barcode')
        barcode_image = request.FILES.get('barcode_image')

        if not barcode and not barcode_image:
            return JsonResponse({'success': False, 'error': 'Either barcode string or barcode_image is required'}, status=400)

        # 1. Get the Barcode string from image if needed
        if not barcode and barcode_image:
            try:
                img = Image.open(barcode_image)
                decoded_objects = decode(img)
                if not decoded_objects:
                    return JsonResponse({'success': False, 'error': 'Could not decode any barcode from the image'}, status=400)
                barcode = decoded_objects[0].data.decode('utf-8')
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Barcode decoding error: {str(e)}'}, status=500)

        # 2. Fetch data from Open Food Facts
        off_data = fetch_product_from_barcode(barcode)
        if "error" in off_data:
            return JsonResponse({'success': False, 'error': off_data["error"]}, status=400)

        ingredients_text = off_data.get("ingredients_text", "")
        nutrition_raw = off_data.get("nutrition", {})
        
        ingredients_list = [i.strip() for i in ingredients_text.split(",") if i.strip()] if ingredients_text else ["No ingredients found for this product"]

        # 3. Load ML models safely
        BASE_PATH = r"E:\backend\backend\ml_models"
        try:
            vectorizer = load_pickle_file(os.path.join(BASE_PATH, 'tfidf_vectorizer.pkl'))
            ingredients_model = load_pickle_file(os.path.join(BASE_PATH, 'random_forest_model.pkl'))
            nutrition_model = load_pickle_file(os.path.join(BASE_PATH, 'chirag_patil.pkl'))
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Model load error: {str(e)}'}, status=500)

        # 4. Score Ingredients
        try:
            ing_text_processed = " ".join(ingredients_list) if ingredients_list else ""
            if not ing_text_processed.strip():
                ingredients_score = 5.0 # default
            else:
                ing_vector = vectorizer.transform([ing_text_processed])
                ingredients_score = float(ingredients_model.predict(ing_vector)[0]) * 10
        except Exception as e:
            ingredients_score = 5.0
            logger.error(f"Ing prediction error: {str(e)}")

        # 5. Score Nutrition
        # Maps from open food facts nutritments to model expectations
        try:
            nutrition_data = {
                "Calories": float(nutrition_raw.get("energy-kcal_100g", 0)),
                "Protein (g)": float(nutrition_raw.get("proteins_100g", 0)),
                "Fats (g)": float(nutrition_raw.get("fat_100g", 0)),
                "Carbohydrates (g)": float(nutrition_raw.get("carbohydrates_100g", 0)),
                "Sugars (g)": float(nutrition_raw.get("sugars_100g", 0)),
                "Sodium (mg)": float(nutrition_raw.get("sodium_100g", 0)) * 1000, # g to mg typically OpenFoodFacts is g
                "Saturated Fat (g)": float(nutrition_raw.get("saturated-fat_100g", 0)),
                "Trans Fat (g)": float(nutrition_raw.get("trans-fat_100g", 0)),
                "Cholesterol (mg)": float(nutrition_raw.get("cholesterol_100g", 0)) * 1000 # g to mg
            }
            
            nutrition_df = pd.DataFrame([nutrition_data])
            prediction = nutrition_model.predict(nutrition_df)
            
            if isinstance(prediction, np.ndarray) and prediction.size > 0:
                if len(prediction[0]) > 1:
                    _, nutrition_score = prediction[0]
                    nutrition_score = float(nutrition_score)
                else:
                    nutrition_score = float(prediction[0])
            else:
                nutrition_score = 0.0
        except Exception as e:
            logger.error(f"Nutrition prediction error: {str(e)}")
            nutrition_score = 5.0

        # Calculate Total
        total_score = (ingredients_score + nutrition_score) / 2.0
        
        formatted_nutrition = {
            "Calories": nutrition_data["Calories"],
            "Protein (g)": nutrition_data["Protein (g)"],
            "Fats (g)": nutrition_data["Fats (g)"],
            "Carbohydrates (g)": nutrition_data["Carbohydrates (g)"],
            "Sugars (g)": nutrition_data["Sugars (g)"],
            "Sodium (mg)": nutrition_data["Sodium (mg)"],
            "Saturated Fat (g)": nutrition_data["Saturated Fat (g)"],
            "Trans Fat (g)": nutrition_data["Trans Fat (g)"],
            "Cholesterol (mg)": nutrition_data["Cholesterol (mg)"]
        }

        try:
            ai_analysis = generate_ai_analysis(
                ingredients_list=ingredients_list,
                nutrition_data=formatted_nutrition,
                ingredients_score=ingredients_score,
                nutrition_score=nutrition_score,
                total_score=total_score,
                user=request.user,
            )
            analysis_summary = generate_analysis_summary(
                ingredients_list=ingredients_list,
                nutrition_data=nutrition_data,
                ingredients_score=ingredients_score,
                nutrition_score=nutrition_score,
                total_score=total_score
            )
        except Exception as e:
            logger.error(f"AI analysis error: {str(e)}")
            ai_analysis = AI_ANALYSIS_FALLBACK.copy()
            analysis_summary = f"This product received a score of {total_score:.1f}/10."

        from django.utils import timezone

        # 7. Save to History
        history = History.objects.create(
            user=request.user,
            ingredients_result=ingredients_score,
            nutrition_result=nutrition_score,
            total_result=total_score,
            nutrition_data=formatted_nutrition,
            ingredients_data={
                "ingredients": ingredients_list,
                "ai_analysis": ai_analysis,
                "product_meta": {
                    "name": off_data.get("name", "Unknown Product"),
                    "brand": off_data.get("brand", "Unknown Brand"),
                    "image": off_data.get("image_front_url", ""),
                },
            },
            analysis_summary=analysis_summary
        )

        return JsonResponse({
            'success': True,
            'history_id': history.id,
            'ingredients': {
                'raw_data': ingredients_list,
                'score': ingredients_score
            },
            'nutrition': {
                'data': formatted_nutrition,
                'score': nutrition_score
            },
            'total_score': total_score,
            'analysis_summary': analysis_summary,
            'ai_analysis': ai_analysis,
            'product_name': off_data.get("name", "Unknown Product"),
            'product_image': off_data.get("image_front_url", ""),
            'product_brand': off_data.get("brand", "Unknown Brand"),
            'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"Barcode scan error: {str(e)}")
        return JsonResponse({'success': False, 'error': f"Processing error: {str(e)}"}, status=500)
