from django import template

from fees.money import money as format_money

register = template.Library()


@register.filter
def money(value):
    return format_money(value)
