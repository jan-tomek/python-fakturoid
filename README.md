# fakturoid.cz Python API

The Python interface to online accounting service [Fakturoid](http://fakturoid.cz/).

Update to [API v3](https://www.fakturoid.cz/api/v3) by Jan Tomek ([jan.tomek@outlook.com](mailto:jan.tomek@outlook.com)).
This library was created and developed by Roman Krejcik ([farin@farin.cz](mailto:farin@farin.cz)).
It is unoficial and no support from Fakturoid team can be claimed.

## Installation

Install from PyPI (not currently available)

    <del>pip install fakturoid</del>

or alternatively install development version directly from github

    pip install -e git+git://github.com/jan-tomek/python-fakturoid#egg=fakturoid


Supported Python versions are ~~2.6+~~ and 3.x. Dependencies are [requests](https://pypi.python.org/pypi/requests),
[python-dateutil](https://pypi.python.org/pypi/python-dateutil/2.1)

## Quickstart

Create context - change to v3 uses client id and client secret:
```python
from fakturoid import Fakturoid

fa = Fakturoid('yourslug', 'your@email.com', 'clientid038dc73...', 'clientsecret7452f8..,','YourApp (yourname@example.com)')
```

Print all regular invoices from year 2024:
```python
from datetime import date

for invoice in fa.invoices(proforma=False, since=date(2024,1,1)):
    print(invoice.number, invoice.total)
```

Delete subject with id 27:
```python
subject = fa.subject(27)
fa.delete(subject)
```

And finally create new invoice:
```python
from fakturoid import Invoice, InvoiceLine

invoice = Invoice(
    subject_id=23205068,
    #number='2025-0108',
    due=10,
    issued_on=date(2025, 1, 31),
    taxable_fulfillment_due=date(2025, 1, 31),
    lines=[
        # use Decimal or string for floating values
        InvoiceLine(name='Hard work', unit_name='h', unit_price=40000, vat_rate=21),
        InvoiceLine(name='Soft material', quantity=12, unit_name='ks', unit_price="4.60", vat_rate=21),
    ]
)
fa.save(invoice)

print(invoice.due_on)
```

## API

<code>Fakturoid.<b>account()</b></code>

Returns `Account` instance. Account is readonly and can't be updated by API.

<code>Fakturoid.<b>subject(id)</b></code>

Returns `Subject` instance.

<code>Fakturoid.<b>subjects(since=None, updated_since=None, custom_id=None)</b></code>

Loads all subjects filtered by args.
If since (`date` or `datetime`) parameter is passed, returns only subjects created since given date.

<code>Fakturoid.<b>subjects.search("General Motors")</b></code>

Perform full text search on subjects

<code>Fakturoid.<b>invoce(id)</b></code>

Returns `Invoice` instance.

<code>Fakturoid.<b>invoices(proforma=None, subject_id=None, since=None, updated_since=None, number=None, status=None, custom_id=None)</b></code>

Use `proforma=False`/`True` parameter to load regular or proforma invoices only.

Returns list of invoices. Invoices are lazily loaded according to slicing.
```python
fa.invoices(status='paid')[:100]   # loads 100 paid invoices
fa.invoices()[-1]   # loads first issued invoice (invoices are ordered from latest to first)
```

<code>Fakturoid.<b>fire_invoice_event(id, event, **args)</b></code>

Fires basic events on invoice. All events are described in [Fakturoid API docs](http://docs.fakturoid.apiary.io/#reference/invoices/invoice-actions/akce-nad-fakturou).

Pay event can accept optional arguments `paid_at` and `paid_amount`
```python
fa.fire_invoice_event(11331402, 'pay', paid_at=date(2024, 11, 17), paid_amount=2000)
```

<code>Fakturoid.<b>generator(id)</b></code>

Returns `Generator` instance.

<code>Fakturoid.<b>generators(recurring=None, subject_id=None, since=None)</b></code>

Use `recurring=False`/`True` parameter to load recurring or simple templates only.

<code>Fakturoid.<b>save(model)</b></code>

Create or modify `Subject`, `Invoice` or `Generator`.

To modify or delete inoive lines simply edit `lines`

```python
invoice = fa.invoices(number='2024-0002')[0]
invoice.lines[0].unit_price = 5000 # edit first item
del invoice.lines[-1]  # delete last item
fa.save(invoice)
```

<code>Fakturoid.<b>delete(model)</b></code><br>

Delete `Subject`, `Invoice` or `Generator`.

```python
subj = fa.subject(1234)
fa.delete(subj)            # delete subject

fa.delete(Subject(id=1234))   # or alternativelly delete is possible without object loading
```

### Models

All models fields are named same as  [Fakturoid API](https://www.fakturoid.cz/api/v3).

Values are mapped to corresponding `int`, `decimal.Decimal`, `datetime.date` and `datetime.datetime` types.

<code>Fakturoid.<b>Account</b></code>

[https://www.fakturoid.cz/api/v3/account](https://www.fakturoid.cz/api/v3/account)

<code>Fakturoid.<b>Subjects</b></code>

[https://www.fakturoid.cz/api/v3/subjects](https://www.fakturoid.cz/api/v3/subjects)

<code>Fakturoid.<b>Invoices</b></code><br>
<code>Fakturoid.<b>InvoiceLine</b></code>

[https://www.fakturoid.cz/api/v3/invoices](https://www.fakturoid.cz/api/v3/invoices)

<code>Fakturoid.<b>Generators</b></code>

[https://www.fakturoid.cz/api/v3/generators](https://www.fakturoid.cz/api/v3/generators)

Use `InvoiceLine` for generator lines

<code>Fakturoid.<b>Invoice Messages</b></code>

[https://www.fakturoid.cz/api/v3/invoice-messages](https://www.fakturoid.cz/api/v3/invoice-messages)
