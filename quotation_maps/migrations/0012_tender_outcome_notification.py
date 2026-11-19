from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("quotation_maps", "0011_map_sequence_three_digits")]

    operations = [
        migrations.CreateModel(
            name="TenderOutcomeNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient_email", models.EmailField(max_length=254)),
                ("status", models.CharField(choices=[("PENDING", "Pendente"), ("SENDING", "Enviando"), ("SENT", "Enviado"), ("FAILED", "Falha")], db_index=True, default="PENDING", max_length=10)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("quotation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outcome_notifications", to="quotation_maps.quotationmap")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="quotation_maps.supplier")),
            ],
        ),
        migrations.AddConstraint(
            model_name="tenderoutcomenotification",
            constraint=models.UniqueConstraint(fields=("quotation", "supplier"), name="unique_tender_outcome_notification"),
        ),
    ]
