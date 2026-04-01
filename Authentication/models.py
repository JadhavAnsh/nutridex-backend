from django.db import models
from django.utils import timezone
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    unique_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    
    # Onboarding data
    weight = models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    bmi = models.FloatField(null=True, blank=True)
    conditions = models.JSONField(default=list, blank=True)

    # Remove the username field
    username = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:     
        db_table = "User"

    def __str__(self):
        return f"{self.full_name}"

class NutritionResult(models.Model):
    # Image reference
    image_path = models.CharField(max_length=255, blank=True, null=True)
    image_name = models.CharField(max_length=100, blank=True, null=True)
    processed_at = models.DateTimeField(default=timezone.now)
    
    calories = models.FloatField(blank=True, null=True)    
    protein = models.FloatField(blank=True, null=True)    
    fats = models.FloatField(blank=True, null=True)    
    carbohydrates = models.FloatField(blank=True, null=True)    
    sugar = models.FloatField(blank=True, null=True)    
    sodium = models.FloatField(blank=True, null=True)    
    fiber = models.FloatField(blank=True, null=True)    
    serving_size = models.FloatField(blank=True, null=True)
    serving_size_unit = models.CharField(max_length=10, blank=True, null=True)    
    energy_100g = models.FloatField(blank=True, null=True)    
    saturated_fat_100g = models.FloatField(blank=True, null=True)    
    trans_fat_100g = models.FloatField(blank=True, null=True)    
    calcium_100g = models.FloatField(blank=True, null=True)    
    iron_100g = models.FloatField(blank=True, null=True)    
    vitamin_a_100g = models.FloatField(blank=True, null=True)    
    vitamin_c_100g = models.FloatField(blank=True, null=True)    
    cholesterol_100g = models.FloatField(blank=True, null=True)    
    def __str__(self):
        return f"Nutrition Result for {self.image_name or 'Unknown'}"
    
class OCRResult(models.Model):
    image = models.ImageField(upload_to='ocr_uploads/')
    extracted_data = models.JSONField()  
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OCRResult {self.id} - {self.created_at}"

class History(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='results')
    
    # Simple score fields
    ingredients_result = models.FloatField(blank=True, null=True)
    nutrition_result = models.FloatField(blank=True, null=True)
    total_result = models.FloatField(blank=True, null=True)

    analysis_summary = models.TextField(blank=True, null=True)
    
    # Structured data fields
    nutrition_data = models.JSONField(default=dict, blank=True)
    ingredients_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result {self.id} - {self.created_at}"
