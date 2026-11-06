from django.test import SimpleTestCase
from PIL import Image
from memorando_remessas.services.nota_fiscal_reader import _national_short_number_from_strokes


class DanfseVisualNumberTest(SimpleTestCase):
    def test_blank_image_does_not_invent_number(self):
        self.assertEqual(_national_short_number_from_strokes(Image.new('RGB', (875, 1280), 'white')), '')

    def test_not_a_generic_document_number_extractor(self):
        self.assertEqual(_national_short_number_from_strokes(Image.new('RGB', (100, 100), 'white')), '')
