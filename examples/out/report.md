# Cleaning report for orders_messy.csv

62 rows in, 40 clean, 22 rejected, 76 cells changed.

## Column names

- ` Customer Name ` became `customer_name`
- `E-mail` became `email`
- `Amount Paid` became `amount`
- `Qty` became `qty`
- `Order Date` became `order_date`

## Changes by rule

- date: 27
- whitespace: 20
- money: 20
- email: 9

## Rejected rows

| row | reason |
|---|---|
| 3 | amount='TBD' is not a valid money |
| 6 | customer_name is blank |
| 7 | amount='€2189' is in €, column is $ |
| 8 | email='kai.ode_at_example.com' is not a valid email |
| 14 | amount='€365' is in €, column is $ |
| 15 | amount='€1609' is in €, column is $ |
| 16 | customer_name is blank |
| 17 | amount='€1515' is in €, column is $ |
| 22 | empty row |
| 30 | amount='€2125' is in €, column is $ |
| 31 | customer_name is blank; amount='€2346' is in €, column is $ |
| 36 | amount='€118' is in €, column is $ |
| 43 | amount='€639' is in €, column is $ |
| 44 | amount='TBD' is not a valid money |
| 47 | customer_name is blank; amount='€307' is in €, column is $ |
| 49 | amount='TBD' is not a valid money |
| 56 | email='HAL.KIM_at_EXAMPLE.COM' is not a valid email |
| 58 | email='ana.moe_at_example.com' is not a valid email |
| 59 | email='ana.lopez_at_example.com' is not a valid email |
| 61 | amount='TBD' is not a valid money; email='ed.ode_at_example.com' is not a valid email |
| 62 | amount='€1127' is in €, column is $ |
| 63 | amount='€2189' is in €, column is $ |

Every changed cell is listed in changes.csv with its row, the old value and the new one.
