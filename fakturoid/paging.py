import itertools
from itertools import islice

from fakturoid import six


class PagedResource(object):
    """List adapter for paged resources. Do not use it unless required
       as it loads all the pages."""

    def __init__(self):
        self.objects = None
        self.pages = {}
        self.item_count = None

    def load_page(self, n):
        raise NotImplementedError("You must implement load_page method.")

    def load_all_pages(self):
        self.objects = []
        self.item_count = 0
        for n in itertools.count():
            try:
                page = self.get_page(n)
                self.objects.extend(page)
                self.item_count += len(page)
            except IndexError:
                # we've reached the end of list
                break

    def ensure_all_pages(self):
        if not self.objects:
            self.load_all_pages()
            
    def get_page(self, n):
        if n in self.pages:
            return self.pages[n]
        page = self.load_page(n)
        if page:
            self.pages[n] = page
            return page
        raise IndexError('index out of range')

    def __len__(self):
        self.ensure_all_pages()
        return self.item_count


    def __getitem__(self, key):
        self.ensure_all_pages()
        if isinstance(key, int):
            if key < 0:
                key = len(self) + key
                if key < 0:
                    raise IndexError('index out of range')
            return self.objects[key]
        elif isinstance(key, slice):
            # TODO support negative step
            return islice(self, *key.indices(len(self)))
        else:
            raise TypeError('list indices must be integers')


class ModelList(PagedResource, six.UnicodeMixin):

    def __init__(self, model_api, endpoint, params=None):
        super(ModelList, self).__init__()
        self.model_api = model_api
        self.endpoint = endpoint
        self.params = params or {}

    def load_page(self, n):
        params = {'page': n + 1}
        params.update(self.params)
        response = self.model_api.session._get(self.endpoint, params=params)
        objects = list(self.model_api.unpack(response))
        return objects

    def __unicode__(self):
        # TODO print if loaded
        if self.objects:
            return "<list of {0} models ({1} items)>".format(
                self.model_api.model_type.__name__, len(self))
        else:
            return "<list of {0} models>".format(self.model_api.model_type.__name__)
