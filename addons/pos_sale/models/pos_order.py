# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    currency_rate = fields.Float("Currency Rate", compute='_compute_currency_rate', store=True, digits=0, readonly=True, help='The rate of the currency to the currency of rate applicable at the date of the order')
    crm_team_id = fields.Many2one('crm.team', string="Sales Team")

    @api.model
    def _complete_values_from_session(self, session, values):
        values = super(PosOrder, self)._complete_values_from_session(session, values)
        values.setdefault('crm_team_id', session.config_id.crm_team_id.id)
        return values

    @api.depends('pricelist_id.currency_id', 'date_order', 'company_id')
    def _compute_currency_rate(self):
        for order in self:
            date_order = order.date_order or fields.Datetime.now()
            order.currency_rate = self.env['res.currency']._get_conversion_rate(order.company_id.currency_id, order.pricelist_id.currency_id, order.company_id, date_order)

    def _prepare_invoice(self):
        invoice_vals = super(PosOrder, self)._prepare_invoice()
        invoice_vals['team_id'] = self.crm_team_id
        return invoice_vals

class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    margin = fields.Float(compute='_product_margin', digits='Product Price', store=True)
    purchase_price = fields.Float(string='Cost', digits='Product Price')

    def _compute_margin(self, order_id, product_id):
        frm_cur = self.env.company.currency_id
        to_cur = order_id.pricelist_id.currency_id
        purchase_price = product_id.standard_price
        purchase_price = product_id.uom_id._compute_price(purchase_price, product_id.uom_id)
        price = frm_cur._convert(
            purchase_price, to_cur, order_id.company_id or self.env.company,
            order_id.date_order or fields.Date.today(), round=False)
        return price

    @api.model
    def _get_purchase_price(self, pricelist, product, product_uom, date):
        frm_cur = self.env.company.currency_id
        to_cur = pricelist.currency_id
        purchase_price = product.standard_price
        if product_uom != product.uom_id:
            purchase_price = product.uom_id._compute_price(purchase_price, product_uom)
        price = frm_cur._convert(
            purchase_price, to_cur,
            self.order_id.company_id or self.env.company,
            date or fields.Date.today(), round=False)
        return {'purchase_price': price}

    @api.onchange('product_id', 'product_uom')
    def product_id_change_margin(self):
        if not self.order_id.pricelist_id or not self.product_id or not self.product_uom:
            return
        self.purchase_price = self._compute_margin(self.order_id, self.product_id, self.product_uom)

    @api.onchange('product_id')
    def product_id_change(self):
        # VFE FIXME : bugfix for matrix, the purchase_price will be changed to a computed field in master.
        res = super(PosOrderLine, self).product_id_change()
        self.product_id_change_margin()
        return res

    @api.model
    def create(self, vals):

        # Calculation of the margin for programmatic creation of a SO line. It is therefore not
        # necessary to call product_id_change_margin manually
        if 'purchase_price' not in vals and ('display_type' not in vals or not vals['display_type']):
            order_id = self.env['pos.order'].browse(vals['order_id'])
            product_id = self.env['product.product'].browse(vals['product_id'])
            #product_uom_id = self.env['uom.uom'].browse(vals['product_uom'])

            vals['purchase_price'] = self._compute_margin(order_id, product_id)

        return super(PosOrderLine, self).create(vals)

    @api.depends('product_id', 'purchase_price', 'qty', 'price_unit', 'price_subtotal')
    def _product_margin(self):
        for line in self:
            currency = line.order_id.pricelist_id.currency_id
            price = line.purchase_price
            margin = line.price_subtotal - (price * line.qty)
            line.margin = currency.round(margin) if currency else margin