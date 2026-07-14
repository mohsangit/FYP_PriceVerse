# Generated migration

from django.db import migrations, models


def backfill_discontinued(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    try:
        from whatmobile.discontinued import is_product_discontinued
    except ImportError:
        return

    for product in Product.objects.prefetch_related("listings").iterator(chunk_size=200):
        flag = is_product_discontinued(product)
        if flag:
            Product.objects.filter(pk=product.pk).update(is_discontinued=True)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0010_seed_sample_reviews"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_discontinued",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["is_discontinued", "-created_at"], name="products_pr_disc_created_idx"),
        ),
        migrations.RunPython(backfill_discontinued, migrations.RunPython.noop),
    ]
