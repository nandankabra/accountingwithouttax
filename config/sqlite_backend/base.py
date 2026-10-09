"""Store accounting decimals as integer minor units, avoiding SQLite floats."""
from decimal import Decimal
from django.db.backends.sqlite3.base import DatabaseWrapper as SQLiteWrapper
from django.db.backends.sqlite3.operations import DatabaseOperations as SQLiteOperations


class ExactDecimalOperations(SQLiteOperations):
    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        if value is None:
            return None
        decimal = Decimal(value)
        units = decimal.scaleb(decimal_places or 0)
        if not units.is_finite() or units != units.to_integral_value() or abs(units) > 2**63 - 1:
            raise ValueError('Decimal value exceeds the exact local database range.')
        return int(units)

    def get_decimalfield_converter(self, expression):
        places = expression.output_field.decimal_places or 0
        def convert(value, expression, connection):
            if value is not None:
                if not isinstance(value, int):
                    raise ValueError('Accounting decimal storage must contain integer minor units.')
                return Decimal(value).scaleb(-places)
        return convert


class DatabaseWrapper(SQLiteWrapper):
    data_types = {**SQLiteWrapper.data_types, 'DecimalField': 'bigint'}
    ops_class = ExactDecimalOperations
