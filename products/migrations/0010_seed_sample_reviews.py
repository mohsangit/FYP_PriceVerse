from django.db import migrations


SAMPLE_REVIEWS = [
    {
        "author_name": "Ayesha Khan",
        "author_role": "Student, Lahore",
        "rating": 5,
        "body": "PriceVerse helped me find the cheapest Samsung Galaxy A series across stores in seconds. "
                "The price comparison saved me from overpaying at the first shop I checked.",
        "highlight_label": "Saved",
        "highlight_value": "Rs. 8,500",
    },
    {
        "author_name": "Bilal Ahmed",
        "author_role": "iPhone Buyer",
        "rating": 5,
        "body": "The discount tracking is brilliant. I got a notification the moment the iPhone I wanted "
                "dropped in price, and the fake-discount detection gave me confidence it was a real deal.",
        "highlight_label": "Price Alerts",
        "highlight_value": "3 triggered",
    },
    {
        "author_name": "Fatima Noor",
        "author_role": "Smart Shopper",
        "rating": 4,
        "body": "I love that everything is in one place — specs, prices from multiple sources, and the "
                "AI assistant answers my questions about Samsung vs Apple instantly.",
        "highlight_label": "Compared",
        "highlight_value": "12 phones",
    },
    {
        "author_name": "Hamza Sheikh",
        "author_role": "Tech Enthusiast",
        "rating": 5,
        "body": "The chatbot actually understands what I ask. I asked for the best iPhone deal under my "
                "budget and it pointed me to the exact listing with the biggest discount.",
        "highlight_label": "Best Deal",
        "highlight_value": "Found fast",
    },
    {
        "author_name": "Sana Tariq",
        "author_role": "Online Shopper",
        "rating": 5,
        "body": "Adding phones to my favorites and getting alerts when prices fall is exactly what I needed. "
                "The sale highlights make it so easy to spot genuine offers.",
        "highlight_label": "Favorites",
        "highlight_value": "Tracking 9",
    },
    {
        "author_name": "Usman Raza",
        "author_role": "Day-to-day Saver",
        "rating": 4,
        "body": "Clean, fast and accurate. The data is pulled live from real stores, so the prices I see "
                "are the prices I actually pay. PriceVerse has become my go-to before any purchase.",
        "highlight_label": "Live Data",
        "highlight_value": "Always fresh",
    },
]


def seed_reviews(apps, schema_editor):
    Review = apps.get_model("products", "Review")
    for data in SAMPLE_REVIEWS:
        Review.objects.get_or_create(
            author_name=data["author_name"],
            is_sample=True,
            defaults={**data, "is_published": True},
        )


def unseed_reviews(apps, schema_editor):
    Review = apps.get_model("products", "Review")
    Review.objects.filter(is_sample=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0009_review"),
    ]

    operations = [
        migrations.RunPython(seed_reviews, unseed_reviews),
    ]
