#!/usr/bin/env python3
"""Bounded live-model regression suite. No database writes or publication.

Synthetic minimal pairs reproduce audited mistakes. Passing does not establish
an error rate on real articles; failing blocks automatic generation.
"""
import time
from editorial_engine import review_scope, EditorialError

CASES = [
 ('provenance', 'The association obtained and published a France Travail presentation about an AI control assistant.',
  'The association leaked a confidential France Travail document.',
  'The association published a France Travail presentation about an AI control assistant.'),
 ('campus', 'Purdue Northwest is piloting an AI literacy requirement. The fall 2026 requirement applies to Purdue West Lafayette.',
  'Purdue Northwest requires AI literacy for the fall 2026 class.',
  'Purdue Northwest is piloting an AI literacy requirement.'),
 ('future_event', 'The event is scheduled for 28 October. This announcement was published on 23 October.',
  'The event took place on 23 October.',
  'The announcement schedules the event for 28 October.'),
 ('subgroup', 'One-third of the surveyed young adults used chatbots for drug information. Half of that subgroup used them monthly.',
  'Half of all surveyed young adults used chatbots monthly.',
  'Half of the subgroup using chatbots for drug information reported monthly use.'),
 ('invented_warning', 'The glossary defines AI and lists medical imaging and diagnosis as examples. It reports no interviews or expert statements.',
  'Experts interviewed for the glossary warned that AI erodes human oversight.',
  'The glossary lists medical imaging and diagnosis as AI applications.'),
 ('metric', 'The theorem bounds generalization error using observed regeneration-cycle lengths.',
  'The theorem bounds training error using observed cycle lengths.',
  'Observed regeneration-cycle lengths enter the bound on generalization error.'),
 ('speed', 'With uncorrelated input positions, both networks follow the same trajectory, but the convolutional network learns P times faster.',
  'The networks learn at the same speed with uncorrelated input samples.',
  'The convolutional network learns P times faster with uncorrelated input positions.'),
 ('comparator', 'The method improves over the base model on all four holdout tasks. A competing method scores higher on one task.',
  'The method fails to improve over the base model on some holdout tasks.',
  'The method improves over the base model on all four holdout tasks, but does not beat every competitor.')]


def evaluate(review=review_scope):
    failed = []; deadline = time.monotonic() + 840
    for name, evidence, wrong, correct in CASES:
        for label, text, should_pass in [('wrong', wrong, False), ('correct', correct, True)]:
            draft = {'editorial_headline': text, 'editorial_deck': '', 'what_happened': '',
                     'why_it_matters': '', 'for_humans': '', 'for_ai': '', 'limitation': '',
                     'body_paragraphs': [], 'claim_status': 'reporting'}
            try:
                review(draft, [{'source_number': 1, 'evidence': evidence, 'evidence_basis': 'full_source'}], deadline)
                passed = True
            except EditorialError as error:
                if error.code not in {'source_scope_review_failed', 'claim_grounding_failed'}:raise
                passed = False
                # These fixtures are synthetic and public; diagnostics contain no private sources.
                print(name + ':' + label + ' ' + error.code + ': ' + error.feedback, flush=True)
            if passed != should_pass:failed.append(name + ':' + label)
            print(name + ':' + label + (' PASS' if passed == should_pass else ' FAIL'), flush=True)
    if failed:raise RuntimeError('Grounding regression failures: ' + ', '.join(failed))
    print('All 16 live grounding checks passed.', flush=True)

if __name__ == '__main__':evaluate()
