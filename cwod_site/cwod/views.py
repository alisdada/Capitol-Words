from operator import itemgetter
import re
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__))+'/../../')

from django.http import HttpResponse
from django.shortcuts import get_list_or_404

from solr.api import most_frequent_phrases, phrase_by_category, phrase_over_time, full_text_search
from piston.handler import BaseHandler
from piston.resource import Resource
from bioguide.models import *


class GenericHandler(BaseHandler):
    
    def __init__(self, func):
        self.func = func
        self.allowed_methods = ('GET', )
        self.allowed_keys = self._allowed_keys()

    def _allowed_keys(self):
        return self.func.func_code.co_varnames[:self.func.func_code.co_argcount]

    def create_results_list(self, data, *args, **kwargs):
        key = data[0]['facet_counts']['facet_fields'].keys()[0]
        data = data[0]['facet_counts']['facet_fields'][key]
        phrases = data[::2]
        counts = data[1::2]

        results_keys = kwargs.get('results_keys', ['phrase', 'count', ])

        results = [dict(zip(results_keys, x)) for x in zip(phrases, counts)]
        return results

    def read(self, request, *args, **kwargs):
        params = {}
        for k, v in request.GET.items():
            params[str(k)] = v

        params.update(kwargs)
        data = self.func([], **params)

        results = self.create_results_list(data, *args, **kwargs)

        data = {'results': results, 'parameters': params, }

        return data


class PopularPhraseHandler(GenericHandler):
    def __init__(self):
        super(PopularPhraseHandler, self).__init__(most_frequent_phrases)


class PhraseByCategoryHandler(GenericHandler):
    def __init__(self):
        super(PhraseByCategoryHandler, self).__init__(phrase_by_category)

    def read(self, request, *args, **kwargs):
        entity_type = kwargs.get('entity_type')
        if entity_type == 'legislator':
            kwargs['results_keys'] = ['bioguide', 'count', ]
        elif entity_type == 'state':
            kwargs['results_keys'] = ['state', 'count', ]
        elif entity_type == 'party':
            kwargs['results_keys'] = ['party', 'count', ]
        return super(PhraseByCategoryHandler, self).read(request, *args, **kwargs)


class PhraseOverTimeHandler(GenericHandler):
    def __init__(self):
        super(PhraseOverTimeHandler, self).__init__(phrase_over_time)

    def create_results_list(self, data):
        key = data[0]['facet_counts']['facet_dates'].keys()[0]
        data = data[0]['facet_counts']['facet_dates'][key]
        
        dates = []
        for k, v in data.iteritems():
            if k.find('T00:00:00Z') > -1:
                date = k.rstrip('T00:00:00Z')
                dates.append({'date': date, 'count': v})

        dates.sort(key=itemgetter('date'))
        return dates


class FullTextSearchHandler(GenericHandler):
    def __init__(self):
        super(FullTextSearchHandler, self).__init__(full_text_search)

    def read(self, request, *args, **kwargs):
        params = {}
        for k, v in request.GET.iteritems():
            params[str(k)] = v
        data = self.func([], **params)
        results = self.create_results_list(data, *args, **kwargs)
        data = {'results': results, 'parameters': params, }
        return data

    def create_results_list(self, data, *args, **kwargs):
        return [{'bioguide': x.get('speaker_bioguide'),
                 'date': re.sub(r'T\d\d\:\d\d:\d\dZ$', '', x['date']),
                 'speaking': x.get('speaking'), 
                 'title': x.get('document_title', ''),
                 'origin_url': create_gpo_url(x.get('crdoc', '')),
                 'speaker_first': x.get('speaker_firstname'),
                 'speaker_last': x.get('speaker_lastname'),
                 'speaker_party': x.get('speaker_party'),
                 'speaker_state': x.get('speaker_state'),
                 } 
                 for x in data[0]['response']['docs'] ]


class LegislatorLookupHandler(BaseHandler):

    def read(self, request, *args, **kwargs):
        bioguide_id = request.GET.get('bioguide_id', None)
        if not bioguide_id:
            return {}

        legislators = get_list_or_404(Legislator, bioguide_id=bioguide_id)
        legislator = legislators[0]

        results = {
                'bioguide_id': bioguide_id,
                'prefix': legislator.prefix,
                'first': legislator.first,
                'last': legislator.last,
                'suffix': legislator.suffix,
                'sessions': [],
                }
        for legislator in legislators:
            results['sessions'].append({'position': legislator.position,
                                        'party': legislator.party,
                                        'state': legislator.state,
                                        'congress': legislator.congress, })
        return results


def create_gpo_url(crdoc):
    """Convert the path used for the crdoc field to
    a URL that can be used to retrieve the full text
    of the document from the GPO.
    """
    m = re.search(r'(CREC-(\d{4}-\d{2}-\d{2}).*?)\.xml', crdoc)
    if not m:
        return ''

    id, date = m.groups()
    url = 'http://origin.www.gpo.gov/fdsys/pkg/CREC-%s/html/%s.htm' % (date, id)
    return url

