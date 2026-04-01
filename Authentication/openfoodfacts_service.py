import requests

def fetch_product_from_barcode(barcode):
    try:
        url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
        headers = {
            "User-Agent": "FoodAIApp/1.0 (info@example.com)"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            return {"error": "Product not found in OpenFoodFacts database. Please check the barcode."}

        if response.status_code != 200:
            return {"error": f"Failed to fetch from OpenFoodFacts. Status code: {response.status_code}"}

        data = response.json()
        if data.get("status") != 1:
            return {"error": "Product not found in OpenFoodFacts database."}

        product = data.get("product", {})

        return {
            "name": product.get("product_name", "Unknown Product"),
            "brand": product.get("brands", "Unknown Brand"),
            "ingredients_text": product.get("ingredients_text", ""),
            "nutrition": product.get("nutriments", {}),
            "image_front_url": product.get("image_front_url", ""),
            "image_ingredients_url": product.get("image_ingredients_url", ""),
            "image_nutrition_url": product.get("image_nutrition_url", "")
        }
    except Exception as e:
        return {"error": str(e)}
