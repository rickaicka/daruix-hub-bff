from copy import deepcopy
from decimal import Decimal
from unittest import TestCase

from budgeting.services.budget_costs import BDI_TEMPLATE, _calculate_bdi


class BdiFormulaTests(TestCase):
    def calculate(self, indirect='2445.08', taxes=True):
        config = deepcopy(BDI_TEMPLATE)
        config['configured'] = True
        rates = {'lucro': '11.65'}
        if taxes:
            rates.update(dict(zip(
                ('ir_imposto_renda_lucro', 'cs_contribuicao_social_lucro',
                 'iss', 'pis', 'cofins', 'diferencas_impostos', 'imposto_sobre_lucro'),
                ('1.5', '1', '5', '.65', '3', '6.39', '1.17'),
            )))
        for row in config['rows']:
            row['values'] = {'percentage': rates.get(row['key'], '0')}
        return _calculate_bdi(
            config,
            direct_cost={'material': Decimal('16800'), 'labor': Decimal('0'),
                         'total': Decimal('16800')},
            di_config={'totals': {'material': '216.30', 'labor': '2228.78',
                                  'total': indirect}},
        )

    def test_pc25017_with_indirect_cost(self):
        result = self.calculate()
        self.assertEqual(result['summary']['tax_amount'], '516.04')
        self.assertEqual(result['summary']['total_sale'], '22003.17')
        self.assertEqual(result['calculated_factor'], '1.309712533610')
        self.assertEqual(result['calculated_percentage'], '30.9713')
        self.assertEqual(result['detail_total_amount'], '2661.54')

    def test_without_indirect_cost(self):
        result = self.calculate(indirect='0')
        self.assertEqual(result['summary']['tax_amount'], '450.48')
        self.assertEqual(result['summary']['total_sale'], '19207.68')

    def test_without_taxes(self):
        result = self.calculate(taxes=False)
        self.assertEqual(result['summary']['tax_amount'], '0.00')
        self.assertEqual(result['summary']['total_sale'], '21487.13')

    def test_di_keeps_precision_used_by_excel(self):
        from budgeting.services.budget_costs import default_di_configuration, _calculate_di
        config = default_di_configuration()
        for row in config['rows']:
            if row['key'] == '04_01':
                row['values'].update(quantity='0.17', labor='13110.4775')
            elif row['key'] == '01_19':
                row['values'].update(quantity='78', material='0.85')
            elif row['key'] == '07_01':
                row['values'].update(quantity='1', material='150')
        result = _calculate_di(config)
        self.assertEqual(Decimal(result['calculation_totals']['total']), Decimal('2445.081175'))
        self.assertEqual(result['totals']['total'], '2445.08')
