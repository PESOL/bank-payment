# -*- coding: utf-8 -*-
# © 2016 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp.addons.account.tests.account_test_classes\
    import AccountingTestCase
from openerp.tools import float_compare
import time
from lxml import etree


class TestSCT(AccountingTestCase):

    def test_sct(self):
        self.company = self.env['res.company']
        self.account_model = self.env['account.account']
        self.move_model = self.env['account.move']
        self.journal_model = self.env['account.journal']
        self.payment_order_model = self.env['account.payment.order']
        self.payment_line_model = self.env['account.payment.line']
        self.partner_bank_model = self.env['res.partner.bank']
        self.attachment_model = self.env['ir.attachment']
        self.invoice_model = self.env['account.invoice']
        self.invoice_line_model = self.env['account.invoice.line']
        company = self.env.ref('base.main_company')
        self.partner_agrolait = self.env.ref('base.res_partner_2')
        self.partner_c2c = self.env.ref('base.res_partner_12')
        self.account_revenue = self.account_model.search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_revenue').id)], limit=1)
        self.account_payable = self.account_model.search([(
            'user_type_id',
            '=',
            self.env.ref('account.data_account_type_payable').id)], limit=1)
        # create journal
        self.bank_journal = self.journal_model.create({
            'name': 'Company Bank journal',
            'type': 'bank',
            'code': 'BNKFB',
            'bank_account_id':
            self.env.ref('account_payment_mode.main_company_iban').id,
            'bank_id':
            self.env.ref('account_payment_mode.bank_la_banque_postale').id,
            })
        # update payment mode
        self.payment_mode = self.env.ref(
            'account_banking_sepa_credit_transfer.'
            'payment_mode_outbound_sepa_ct1')
        self.payment_mode.write({
            'bank_account_link': 'fixed',
            'fixed_journal_id': self.bank_journal.id,
            })
        eur_currency_id = self.env.ref('base.EUR').id
        company.currency_id = eur_currency_id
        invoice = self.invoice_model.create({
            'partner_id': self.partner_agrolait.id,
            'reference_type': 'none',
            'reference': 'F124212',
            'currency_id': eur_currency_id,
            'name': 'test 1',
            'account_id': self.account_payable.id,
            'type': 'in_invoice',
            'date_invoice': time.strftime('%Y-%m-%d'),
            'payment_mode_id': self.payment_mode.id,
            'partner_bank_id':
            self.env.ref('account_payment_mode.res_partner_2_iban').id,
            })
        self.invoice_line_model.create({
            'invoice_id': invoice.id,
            'price_unit': 42.0,
            'quantity': 1,
            'name': 'Great service',
            'account_id': self.account_revenue.id,
            })
        invoice.signal_workflow('invoice_open')
        action = invoice.create_account_payment_line()
        self.assertEquals(action['res_model'], 'account.payment.order')
        self.payment_order = self.payment_order_model.browse(action['res_id'])
        self.assertEquals(
            self.payment_order.payment_type, 'outbound')
        self.assertEquals(
            self.payment_order.payment_mode_id, invoice.payment_mode_id)
        self.assertEquals(
            self.payment_order.journal_id, self.bank_journal)
        pay_lines = self.payment_line_model.search([
            ('partner_id', '=', self.partner_agrolait.id)])
        self.assertEquals(len(pay_lines), 1)
        agrolait_pay_line = pay_lines[0]
        precision = self.env['decimal.precision'].precision_get('Account')
        self.assertEquals(agrolait_pay_line.currency_id.id, eur_currency_id)
        self.assertEquals(
            agrolait_pay_line.partner_bank_id, invoice.partner_bank_id)
        self.assertEquals(float_compare(
            agrolait_pay_line.amount_currency, 42, precision_digits=precision),
            0)
        self.assertEquals(agrolait_pay_line.communication_type, 'normal')
        self.assertEquals(agrolait_pay_line.communication, 'F124212')
        self.payment_order.draft2open()
        self.assertEquals(self.payment_order.state, 'open')
        self.assertEquals(self.payment_order.sepa, True)
        action = self.payment_order.open2generated()
        self.assertEquals(self.payment_order.state, 'generated')
        self.assertEquals(action['res_model'], 'ir.attachment')
        attachment = self.attachment_model.browse(action['res_id'])
        self.assertEquals(attachment.datas_fname[-4:], '.xml')
        xml_file = attachment.datas.decode('base64')
        xml_root = etree.fromstring(xml_file)
        # print "xml_file=", etree.tostring(xml_root, pretty_print=True)
        namespaces = xml_root.nsmap
        namespaces['p'] = xml_root.nsmap[None]
        namespaces.pop(None)
        pay_method_xpath = xml_root.xpath(
            '//p:PmtInf/p:PmtMtd', namespaces=namespaces)
        self.assertEquals(pay_method_xpath[0].text, 'TRF')
        sepa_xpath = xml_root.xpath(
            '//p:PmtInf/p:PmtTpInf/p:SvcLvl/p:Cd', namespaces=namespaces)
        self.assertEquals(sepa_xpath[0].text, 'SEPA')
        debtor_acc_xpath = xml_root.xpath(
            '//p:PmtInf/p:DbtrAcct/p:Id/p:IBAN', namespaces=namespaces)
        self.assertEquals(
            debtor_acc_xpath[0].text,
            self.payment_order.company_partner_bank_id.sanitized_acc_number)
        self.payment_order.generated2uploaded()
        self.assertEquals(self.payment_order.state, 'uploaded')
        self.assertEquals(invoice.state, 'paid')
        return
