import re
import json
from datetime import date, datetime
from functools import wraps
from base64 import b64encode

import requests

from fakturoid.models import Account, BankAccount, Expense, Generator, Invoice, InvoiceMessage, InvoicePayment, Subject
from fakturoid.paging import ModelList

__all__ = ['Fakturoid']

link_header_pattern = re.compile(r'page=(\d+)[^>]*>; rel="last"')


class Fakturoid(object):
    """Fakturoid API v3 - https://www.fakturoid.cz/api/v3"""
    slug = None
    api_key = None
    user_agent = 'python-fakturoid (https://github.com/jan-tomek/python-fakturoid)'

    _models_api = None

    def __init__(self, slug, email, client_id, client_secret, user_agent=None):
        self.slug = slug
        self.client_id_secret = client_id + ':' + client_secret
        self.email = email
        self.user_agent = user_agent or self.user_agent

        resp = requests.request(method='POST',
                             url='https://app.fakturoid.cz/api/v3/oauth/token',
                             headers={'User-Agent': self.user_agent,
                                      'Accept': 'application/json',
                                      'Authorization': 'Basic ' + b64encode(self.client_id_secret.encode()).decode()},
                             data ={'grant_type': 'client_credentials'},
                             )
        try:
            self.token = json.loads(resp.text)['access_token']
        except Exception:
            resp.raise_for_status()

        self._models_api = {
            Account: AccountApi(self),
            BankAccount: BankAccountsApi(self),
            Subject: SubjectsApi(self),
            Invoice: InvoicesApi(self),
            Expense: ExpensesApi(self),
            Generator: GeneratorsApi(self),
            InvoiceMessage: MessagesApi(self),
            InvoicePayment: PaymentsApi(self),
        }

        # Hack to expose full seach on subjects as
        #
        #     fa.subjects.search()
        #
        # TODO Keep this API but make internal code redesing in future.
        def subjects_find(*args, **kwargs):
            return self._subjects_find(*args, **kwargs)

        def subjects_search(*args, **kwargs):
            return self._subjects_search(*args, **kwargs)
        self.subjects = subjects_find
        self.subjects.search = subjects_search

    def model_api(model_type=None):
        def wrap(fn):
            @wraps(fn)
            def wrapper(self, *args, **kwargs):
                mt = model_type or type(args[0])
                mapi = self._models_api.get(mt)
                if not mapi:
                    raise TypeError('model expected, got {0}'.format(mt.__name__))
                return fn(self, mapi, *args, **kwargs)
            return wrapper
        return wrap

    def account(self):
        return self._models_api[Account].load()

    def bank_accounts(self):
        return self._models_api[BankAccount].find()

    @model_api(Subject)
    def subject(self, mapi, id):
        return mapi.load(id)

    @model_api(Subject)
    def _subjects_find(self, mapi, *args, **kwargs):
        """call using fa.subjects()"""
        return mapi.find(*args, **kwargs)

    @model_api(Subject)
    def _subjects_search(self, mapi, *args, **kwargs):
        """call using fa.subjects.search()"""
        return mapi.search(*args, **kwargs)

    @model_api(Invoice)
    def invoice(self, mapi, id):
        return mapi.load(id)

    @model_api(Invoice)
    def invoices(self, mapi, *args, **kwargs):
        return mapi.find(*args, **kwargs)

    @model_api(Invoice)
    def fire_invoice_event(self, mapi, id, event, **kwargs):
        return mapi.fire(id, event, **kwargs)

    @model_api(Expense)
    def expense(self, mapi, id):
        return mapi.load(id)

    @model_api(Expense)
    def expenses(self, mapi, *args, **kwargs):
        return mapi.find(*args, **kwargs)

    @model_api(Expense)
    def fire_expense_event(self, mapi, id, event, **kwargs):
        return mapi.fire(id, event, **kwargs)

    @model_api(Generator)
    def generator(self, mapi, id):
        return mapi.load(id)

    @model_api(Generator)
    def generators(self, mapi, *args, **kwargs):
        return mapi.find(*args, **kwargs)

    @model_api(InvoicePayment)
    def create_tax_document(self, mapi, invoice_id, payment_id, **kwargs):
        return mapi.create_tax_document(invoice_id, payment_id, **kwargs)

    @model_api()
    def save(self, mapi, obj, **kwargs):
        mapi.save(obj, **kwargs)

    @model_api()
    def delete(self, mapi, obj, **kwargs):
        """Call with loaded model or use new instance directly.
        s = fa.subject(1234)
        a.delete(s)

        fa.delete(Subject(id=1234))
        """
        mapi.delete(obj, **kwargs)

    def _extract_page_link(self, header):
        m = link_header_pattern.search(header)
        if m:
            return int(m.group(1))
        return None

    def _make_request(self, method, success_status, endpoint, **kwargs):
        url = "https://app.fakturoid.cz/api/v3/accounts/{0}/{1}.json".format(self.slug, endpoint)
        headers = {'User-Agent': self.user_agent,
                   'Authorization': 'Bearer ' + self.token,}
        headers.update(kwargs.pop('headers', {}))
        r = getattr(requests, method)(url, headers=headers, **kwargs)
        try:
            json_result = r.json()
        except Exception:
            json_result = None

        if r.status_code == success_status:
            response = {'json': json_result}
            if 'link' in r.headers:
                page_count = self._extract_page_link(r.headers['link'])
                if page_count:
                    response['page_count'] = page_count
            return response

        if json_result and "errors" in json_result:
            raise ValueError(json_result["errors"])

        r.raise_for_status()

    def _get(self, endpoint, params=None):
        return self._make_request('get', 200, endpoint, params=params)

    def _post(self, endpoint, data, params=None):
        return self._make_request('post', 201, endpoint, headers={'Content-Type': 'application/json'}, data=json.dumps(data), params=params)

    def _put(self, endpoint, data):
        return self._make_request('put', 200, endpoint, headers={'Content-Type': 'application/json'}, data=json.dumps(data))

    def _delete(self, endpoint):
        return self._make_request('delete', 204, endpoint)


class ModelApi(object):
    session = None
    model_type = None
    endpoint = None

    def __init__(self, session):
        self.session = session

    def extract_id(self, value):
        if isinstance(value, int):
            return value
        if not isinstance(value, self.model_type):
            raise TypeError("int or {0} expected".format(self.model_type.__name__.lower()))
        if not getattr(value, 'id', None):
            raise ValueError("object wit unassigned id")
        return value.id

    def unpack(self, response):
        raw = response['json']
        if isinstance(raw, list):
            objects = []
            for fields in raw:
                objects.append(self.model_type(**fields))
            return objects
        else:
            return self.model_type(**raw)


class CrudModelApi(ModelApi):
    def load(self, id):
        if not isinstance(id, int):
            raise TypeError('id must be int')
        response = self.session._get('{0}/{1}'.format(self.endpoint, id))
        return self.unpack(response)

    def find(self, params={}, endpoint=None):
        response = self.session._get(endpoint or self.endpoint, params=params)
        return self.unpack(response)

    def save(self, model):
        if model.id:
            result = self.session._put('{0}/{1}'.format(self.endpoint, model.id), model.get_fields())
        else:
            result = self.session._post(self.endpoint, model.get_fields())
        model.update(result['json'])

    def delete(self, model, **kwargs):
        id = self.extract_id(model)
        self.session._delete('{0}/{1}'.format(self.endpoint, id))


class AccountApi(ModelApi):
    model_type = Account
    endpoint = 'account'

    def load(self):
        response = self.session._get(self.endpoint)
        return self.unpack(response)


class BankAccountsApi(ModelApi):
    model_type = BankAccount
    endpoint = 'bank_accounts'

    def find(self, params={}, endpoint=None):
        response = self.session._get(endpoint or self.endpoint, params=params)
        return self.unpack(response)

class SubjectsApi(CrudModelApi):
    model_type = Subject
    endpoint = 'subjects'

    def find(self, since=None, updated_since=None, custom_id=None):
        params = {}
        if since:
            if not isinstance(since, (datetime, date)):
                raise TypeError("'since' parameter must be date or datetime")
            params['since'] = since.isoformat()
        if updated_since:
            if not isinstance(updated_since, (datetime, date)):
                raise TypeError("'updated_since' parameter must be date or datetime")
            params['updated_since'] = updated_since.isoformat()
        if custom_id:
            params['custom_id'] = custom_id
        return ModelList(self, self.endpoint, params)

    def search(self, query):
        """Full text search as described in
        https://fakturoid.docs.apiary.io/#reference/subjects/subjects-collection-fulltext-search/fulltextove-vyhledavani-v-kontaktech
        """
        if not isinstance(query, str):
            raise TypeError("'query' parameter must be str")
        response = self.session._get('subjects/search'.format(self.endpoint), {'query': query})
        return self.unpack(response)


class InvoicesApi(CrudModelApi):
    """If number argument is givent returms single Invoice object (or None),
    otherwise iterable list of invoices are returned.
    """
    model_type = Invoice
    endpoint = 'invoices'

    TYPES = ['regular', 'proforma', 'correction', 'tax_document']
    STATUSES = ['open', 'sent', 'overdue', 'paid', 'cancelled']
    EVENTS = ['mark_as_sent', 'deliver', 'pay', 'pay_proforma', 'pay_partial_proforma', 'remove_payment', 'deliver_reminder', 'cancel', 'undo_cancel']
    EVENT_ARGS = {
        'pay': {'paid_at', 'paid_amount'}
    }

    def fire(self, invoice_id, event, **kwargs):
        if not isinstance(invoice_id, int):
            raise TypeError('invoice_id must be int')
        if event not in self.EVENTS:
            raise ValueError('invalid event, expected one of {0}'.format(', '.join(self.EVENTS)))

        allowed_args = self.EVENT_ARGS.get(event, set())
        if not set(kwargs.keys()).issubset(allowed_args):
            msg = "invalid event arguments, only {0} can be used with {1}".format(', '.join(allowed_args), event)
            raise ValueError(msg)

        params = {'event': event}
        params.update(kwargs)

        if 'paid_at' in params:
            if not isinstance(params['paid_at'], date):
                raise TypeError("'paid_at' argument must be date")
            params['paid_at'] = params['paid_at'].isoformat()

        self.session._post('invoices/{0}/fire'.format(invoice_id), {}, params=params)

    def find(self, proforma=None, subject_id=None, since=None, until=None, updated_since=None, updated_until=None, number=None, status=None, custom_id=None):
        params = {}
        if subject_id:
            if not isinstance(subject_id, int):
                raise TypeError("'subject_id' parameter must be int")
            params['subject_id'] = subject_id
        if since:
            if not isinstance(since, (datetime, date)):
                raise TypeError("'since' parameter must be date or datetime")
            params['since'] = since.isoformat()
        if until:
            if not isinstance(until, (datetime, date)):
                raise TypeError("'until' parameter must be date or datetime")
            params['until'] = until.isoformat()
        if updated_since:
            if not isinstance(updated_since, (datetime, date)):
                raise TypeError("'updated_since' parameter must be date or datetime")
            params['updated_since'] = updated_since.isoformat()
        if updated_until:
            if not isinstance(updated_until, (datetime, date)):
                raise TypeError("'updated_until' parameter must be date or datetime")
            params['updated_until'] = updated_until.isoformat()
        if number:
            params['number'] = number
        if custom_id:
            params['custom_id'] = custom_id
        if status:
            if status not in self.STATUSES:
                raise ValueError('invalid invoice status, expected one of {0}'.format(', '.join(self.STATUSES)))
            params['status'] = status

        if proforma is not None:
            if proforma:
                params['document_type'] = 'proforma'
            else:
                params['document_type'] = 'regular'

        return ModelList(self, self.endpoint, params)


class ExpensesApi(CrudModelApi):
    """If number argument is givent returms single Expense object (or None),
    otherwise iterable list of expenses are returned.
    """
    model_type = Expense
    endpoint = 'expenses'

    STATUSES = ['open', 'overdue', 'paid']
    EVENTS = ['remove_payment', 'deliver', 'pay', 'lock', 'unlock']
    EVENT_ARGS = {
        'pay': {'paid_on', 'paid_amount', 'variable_symbol', 'bank_account_id'}
    }

    def fire(self, expense_id, event, **kwargs):
        if not isinstance(expense_id, int):
            raise TypeError('expense_id must be int')
        if event not in self.EVENTS:
            raise ValueError('invalid event, expected one of {0}'.format(', '.join(self.EVENTS)))

        allowed_args = self.EVENT_ARGS.get(event, set())
        if not set(kwargs.keys()).issubset(allowed_args):
            msg = "invalid event arguments, only {0} can be used with {1}".format(', '.join(allowed_args), event)
            raise ValueError(msg)

        params = {'event': event}
        params.update(kwargs)

        if 'paid_on' in params:
            if not isinstance(params['paid_on'], date):
                raise TypeError("'paid_on' argument must be date")
            params['paid_on'] = params['paid_on'].isoformat()

        self.session._post('expenses/{0}/fire'.format(expense_id), {}, params=params)

    def find(self, subject_id=None, since=None, updated_since=None, number=None, status=None, custom_id=None, variable_symbol=None):
        params = {}
        if subject_id:
            if not isinstance(subject_id, int):
                raise TypeError("'subject_id' parameter must be int")
            params['subject_id'] = subject_id
        if since:
            if not isinstance(since, (datetime, date)):
                raise TypeError("'since' parameter must be date or datetime")
            params['since'] = since.isoformat()
        if updated_since:
            if not isinstance(updated_since, (datetime, date)):
                raise TypeError("'updated_since' parameter must be date or datetime")
            params['updated_since'] = updated_since.isoformat()
        if number:
            params['number'] = number
        if custom_id:
            params['custom_id'] = custom_id
        if status:
            if status not in self.STATUSES:
                raise ValueError('invalid invoice status, expected one of {0}'.format(', '.join(self.STATUSES)))
            params['status'] = status
        if variable_symbol:
            params['variable_symbol'] = variable_symbol

        return ModelList(self, self.endpoint, params)


class GeneratorsApi(CrudModelApi):
    model_type = Generator
    endpoint = 'generators'

    def find(self, recurring=None, subject_id=None, since=None):
        params = {}
        if subject_id:
            if not isinstance(subject_id, int):
                raise TypeError("'subject_id' parameter must be int")
            params['subject_id'] = subject_id
        if since:
            if not isinstance(since, (datetime, date)):
                raise TypeError("'since' parameter must be date or datetime")
            params['since'] = since.isoformat()

        if recurring is None:
            endpoint = self.endpoint
        elif recurring:
            endpoint = '{0}/recurring'.format(self.endpoint)
        else:
            endpoint = '{0}/template'.format(self.endpoint)

        return super(GeneratorsApi, self).find(params, endpoint)


class MessagesApi(ModelApi):
    model_type = InvoiceMessage
    endpoint = 'message'

    def save(self, model, **kwargs):
        invoice_id = kwargs.get('invoice_id')
        if not isinstance(invoice_id, int):
            raise TypeError("invoice_id must be int")
        self.session._post('invoices/{0}/{1}'.format(invoice_id, self.endpoint), model.get_fields())


class PaymentsApi(ModelApi):
    model_type = InvoicePayment
    endpoint = 'payments'

    def save(self, model, **kwargs):
        invoice_id = kwargs.get('invoice_id')
        if not isinstance(invoice_id, int):
            raise TypeError("invoice_id must be int")
        result = self.session._post('invoices/{0}/{1}'.format(invoice_id, self.endpoint), model.get_fields())
        model.update(result['json'])

    def delete(self, model,  **kwargs):
        invoice_id = kwargs.get('invoice_id')
        if not isinstance(invoice_id, int):
            raise TypeError("invoice_id must be int")
        model_id = self.extract_id(model)
        self.session._delete('invoices/{0}/{1}/{2}'.format(invoice_id, self.endpoint, model_id))

    def create_tax_document(self, model, **kwargs):
        invoice_id = kwargs.get('invoice_id')
        if not isinstance(invoice_id, int):
            raise TypeError("invoice_id must be int")
        model_id = self.extract_id(model)
        result = self.session._post(
            'invoices/{0}/{1}/{2}/create_tax_document'.format(invoice_id, self.endpoint, model_id),
            model.get_fields()
        )
        model.update(result['json'])
