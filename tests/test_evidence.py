import unittest
from storyforge.contracts import delta, review, ContractError
from storyforge.evidence import passages, payload

PROSE = ('The struts were pristine.\n\nThe metal was dark, smooth, and coated in fresh grease.\n\n'
         '"The vibration travels down the line. If the struts are compromised, the whole assembly can shear off. '
         'That’s why I had to... stabilize the gear train."')


def memory(**extra):
    return {'kind':'event', 'text':'Mara inspected the struts.', 'known_by':['mara'], **extra}


class EvidenceTests(unittest.TestCase):
    def test_whitespace_only_quote_difference_preserves_original_span(self):
        raw = memory(evidence='The struts were pristine. The metal was dark, smooth, and coated in fresh grease.')
        result = delta({'memories':[raw]}, PROSE, ['mara'])['memories'][0]
        self.assertIn(result['evidence'], PROSE)
        self.assertIn('\n\n', result['evidence'])
        self.assertNotIn('\n', raw['evidence'])  # Raw model proposal remains untouched.

    def test_quote_wrappers_and_smart_apostrophes(self):
        raw = memory(evidence='"If the struts are compromised, the whole assembly can shear off. That\'s why I had to... stabilize the gear train."')
        result = delta({'memories':[raw]}, PROSE, ['mara'])['memories'][0]
        self.assertIn(result['evidence'], PROSE)
        self.assertIn('That’s', result['evidence'])

    def test_passage_ids_resolve_exact_text_and_offsets(self):
        result = delta({'memories':[memory(evidence_ids=['p001','p002'])]},PROSE,['mara'])['memories'][0]
        self.assertEqual(result['evidence'], PROSE[:PROSE.index('\n\n"')])
        self.assertEqual(result['evidence_match'],'passage_ids')
        for span in result['evidence_spans']:
            self.assertEqual(PROSE[span['start']:span['end']], next(p['text'] for p in passages(PROSE) if p['id']==span['id']))
        self.assertEqual([p['id'] for p in payload(PROSE)['evidence_passages']],['p001','p002','p003'])

    def test_invented_or_ambiguous_evidence_stays_rejected(self):
        for proposal in [memory(evidence_ids=['p999']), memory(evidence='The struts were rusty and broken.'), memory(evidence_ids='p001')]:
            with self.assertRaises(ContractError):
                delta({'memories':[proposal]},PROSE,['mara'])
        with self.assertRaises(ContractError):
            delta({'memories':[memory(evidence='The  old bell rang.') ]},'The old bell rang.\n\nThe old bell rang.',['mara'])

    def test_bound_evidence_cannot_move_to_changed_prose(self):
        bound = delta({'memories':[memory(evidence_ids=['p001'])]},PROSE,['mara'])
        with self.assertRaises(ContractError):
            delta(bound,PROSE+' New scene.',['mara'])

    def test_review_quote_uses_same_source_binding(self):
        result=review({'pass':False,'issues':[{'severity':'blocking','category':'test','quote':'The struts were pristine. The metal was dark, smooth, and coated in fresh grease.','problem':'Test','fix':'Test'}]},PROSE)
        self.assertIn(result['issues'][0]['quote'],PROSE)

    def test_bad_record_shapes_have_controlled_errors(self):
        with self.assertRaises(ContractError):
            delta({'memories':['wrong shape']},PROSE,['mara'])
        with self.assertRaises(ContractError):
            review({'pass':True,'issues':['wrong shape']},PROSE)

if __name__ == '__main__':
    unittest.main()
