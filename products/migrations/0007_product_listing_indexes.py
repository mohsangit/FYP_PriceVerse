from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0006_scrapedlisting_discount_pct_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["-created_at"], name="products_pr_created_4b8f0d_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["brand"], name="products_pr_brand_4c0f1a_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["title"], name="products_pr_title_9a2e3b_idx"),
        ),
        migrations.AddIndex(
            model_name="scrapedlisting",
            index=models.Index(fields=["product_url"], name="products_sc_product_7d1c2e_idx"),
        ),
        migrations.AddIndex(
            model_name="scrapedlisting",
            index=models.Index(fields=["-last_scraped_at"], name="products_sc_last_sc_8e4f1a_idx"),
        ),
    ]
