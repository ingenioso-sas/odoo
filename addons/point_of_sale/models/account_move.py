# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    pos_order_ids = fields.One2many('pos.order', 'account_move')
    pos_payment_ids = fields.One2many('pos.payment', 'account_move_id')

    def _stock_account_get_last_step_stock_moves(self):
        stock_moves = super(AccountMove, self)._stock_account_get_last_step_stock_moves()
        for invoice in self.filtered(lambda x: x.type == 'out_invoice'):
            stock_moves += invoice.sudo().mapped('pos_order_ids.picking_id.move_lines').filtered(lambda x: x.state == 'done' and x.location_dest_id.usage == 'customer')
        for invoice in self.filtered(lambda x: x.type == 'out_refund'):
            stock_moves += invoice.sudo().mapped('pos_order_ids.picking_id.move_lines').filtered(lambda x: x.state == 'done' and x.location_id.usage == 'customer')
        return stock_moves

    def _get_invoiced_lot_values(self):
        self.ensure_one()

        lot_values = super(AccountMove, self)._get_invoiced_lot_values()

        if self.state == 'draft':
            return lot_values

        # user may not have access to POS orders, but it's ok if they have
        # access to the invoice
        for order in self.sudo().pos_order_ids:
            for line in order.lines:
                lots = line.pack_lot_ids or False
                if lots:
                    for lot in lots:
                        lot_values.append({
                            'product_name': lot.product_id.name,
                            'quantity': line.qty if lot.product_id.tracking == 'lot' else 1.0,
                            'uom_name': line.product_uom_id.name,
                            'lot_name': lot.lot_name,
                        })

        return lot_values

    def _get_reconciled_vals(self, partial, amount, counterpart_line):
        """Add pos_payment_name field in the reconciled vals to be able to show the payment method in the invoice."""
        result = super()._get_reconciled_vals(partial, amount, counterpart_line)
        if counterpart_line.move_id.sudo().pos_payment_ids:
            pos_payment = counterpart_line.move_id.sudo().pos_payment_ids
            result['pos_payment_name'] = pos_payment.payment_method_id.name
        return result

    # def _compute_amount(self):
    #     super(AccountMove, self)._compute_amount()
    #     for inv in self:
    #         if inv.type in ['out_invoice', 'out_refund'] and inv.pos_order_ids and any(s != 'closed' for s in inv.pos_order_ids.mapped('session_id.state')):
    #             inv.invoice_payment_state = 'paid'
    #
    # def _tax_tags_need_inversion(self, move, is_refund, tax_type):
    #     # POS order operations are handled by the tax report just like invoices ;
    #     # we should never invert their tags.
    #     if move.type == 'entry':
    #         orders_count = self.env['pos.order'].search_count([('account_move', '=', move._origin.id)])
    #         sessions_count = self.env['pos.session'].search_count([('move_id', '=', move._origin.id)])
    #         if orders_count + sessions_count:
    #             return False
    #     return super()._tax_tags_need_inversion(move, is_refund, tax_type)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _stock_account_get_anglo_saxon_price_unit(self):
        self.ensure_one()
        if not self.product_id:
            return self.price_unit
        price_unit = super(AccountMoveLine, self)._stock_account_get_anglo_saxon_price_unit()
        order = self.move_id.pos_order_ids
        if order:
            price_unit = - order._get_pos_anglo_saxon_price_unit(self.product_id, self.move_id.partner_id.id, self.quantity)
        return price_unit

    # def _get_not_entry_condition(self, aml):
    #     # Overridden so that sale entry moves created par POS still have their amount inverted
    #     # in _compute_tax_audit()
    #     rslt = super()._get_not_entry_condition(aml)
    #
    #     sessions_count = self.env['pos.session'].search_count([('move_id', '=', aml.move_id.id)])
    #     pos_orders_count = self.env['pos.order'].search_count([('account_move', '=', aml.move_id.id)])
    #
    #     return rslt or (sessions_count + pos_orders_count)
    #
    # def _get_refund_tax_audit_condition(self, aml):
    #     # Overridden so that the returns can be detected as credit notes by the tax audit computation
    #     rslt = super()._get_refund_tax_audit_condition(aml)
    #
    #     if aml.move_id.is_invoice():
    #         # We don't need to check the pos orders for this move line if an invoice
    #         # is linked to it ; we know that the invoice type tells us whether it's a refund
    #         return rslt
    #
    #     sessions_count = self.env['pos.session'].search_count([('move_id', '=', aml.move_id.id)])
    #     pos_orders_count = self.env['pos.order'].search_count([('account_move', '=', aml.move_id.id)])
    #
    #     return rslt or (sessions_count + pos_orders_count and aml.debit > 0)
