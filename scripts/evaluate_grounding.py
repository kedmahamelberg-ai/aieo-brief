#!/usr/bin/env python3
"""Bounded live-model regression suite. No database writes or publication.

Synthetic minimal pairs reproduce audited mistakes. Passing does not establish
an error rate on real articles; failing blocks automatic generation.
"""
import time
import copy
from editorial_engine import review_scope, EditorialError

REVIEW_RETRIES = 2

CASES = [
 ('provenance', 'The association obtained and published a France Travail presentation about an AI control assistant.',
  'The association leaked a confidential France Travail document.',
  'The association published a France Travail presentation about an AI control assistant.'),
 ('campus', 'Purdue Northwest is piloting an AI literacy requirement. The fall 2026 requirement applies to Purdue West Lafayette.',
  'Purdue Northwest requires AI literacy for the fall 2026 class.',
  'Purdue Northwest is piloting an AI literacy requirement.'),
 ('future_event', 'The event is scheduled for 28 October. This announcement was published on 23 October.',
  'The event took place on 23 October.',
  'The event is scheduled for 28 October.'),
 ('subgroup', 'One-third of the surveyed young adults used chatbots for drug information. Half of that subgroup used them monthly.',
  'Half of all surveyed young adults used chatbots monthly.',
  'Half of the subgroup using chatbots for drug information used them monthly.'),
 ('invented_warning', 'The glossary defines AI and lists medical imaging and diagnosis as examples. It reports no interviews or expert statements.',
  'Experts interviewed for the glossary warned that AI erodes human oversight.',
  'The glossary lists medical imaging and diagnosis as AI applications.'),
 ('metric', 'The theorem bounds generalization error using observed regeneration-cycle lengths.',
  'The theorem bounds training error using observed cycle lengths.',
  'Observed regeneration-cycle lengths enter the bound on generalization error.'),
 ('speed', 'With uncorrelated input positions, both networks follow the same trajectory, but the convolutional network learns P times faster.',
  'The networks learn at the same speed with uncorrelated input samples.',
  'With uncorrelated input positions, the networks follow the same trajectory, while the convolutional network learns P times faster.'),
 ('comparator', 'The method improves over the base model on all four holdout tasks. A competing method scores higher on one task.',
  'The method fails to improve over the base model on some holdout tasks.',
  'The method improves over the base model on all four holdout tasks, but does not beat every competitor.'),
 ('source_position', 'In this opinion essay, the writer calls generative AI harmful and argues that artists should reject it.',
  'The writer advocates adopting AI without condemning the technology.',
  'The opinion writer argues that artists should reject generative AI.'),
 ('clinical_comparator', 'Brain and spine protocol accuracy was lower than for other scan types but comparable to staff decisions.',
  'The tool performed worse than staff on brain and spine protocols.',
  'Brain and spine protocol accuracy was described as comparable to staff decisions.'),
 ('classroom_scope', 'An accounting educator describes one classroom episode in an opinion essay. The essay reports no representative survey of students.',
  'The study finds that students generally prefer AI to learning independently.',
  'An accounting educator describes one classroom episode in an opinion essay.'),
 ('perspective_scope', 'The published Perspective proposes a legal framework connecting responsibility to human intentions. This supplied text is the abstract, not the complete paper. It reports no experiment.',
  'The experiment proves that the proposed accountability system works.',
  'The supplied abstract describes a published Perspective proposing a legal framework for responsibility.'),
 ('translated_identity', 'The interview identifies the mathematician as 英格丽·多贝西 (Ingrid Daubechies), who discusses AI assistance.',
  'Mathematician Dobensky discusses AI assistance in the interview.',
  'Mathematician Ingrid Daubechies discusses AI assistance in the interview.'),
 ('projected_benefit', 'The provider estimates the tool could save 300 staff hours a year. No realised time saving has yet been measured.',
  'The tool has saved 300 staff hours a year.',
  'The provider estimates a potential saving of 300 staff hours a year.'),
 ('country_context', 'This French-language article analyses expected AI growth across Asian economies. It does not describe an AI deployment in France.',
  'France deploys AI in the economic programme described by the article.',
  'The French-language article analyses expected AI growth across Asian economies.'),
 ('harmful_bypass', 'The malware tries another model after a refusal, attempting to bypass safeguards and produce the attacker’s assessment.',
  'Model chaining provides safety safeguards for the malware process.',
  'The malware tries another model in an attempt to bypass safeguards.'),
 ('qualitative_method', 'Researchers interviewed 18 artists and collaborators about creative work. This was qualitative research, with no controlled creativity experiment.',
  'A controlled experiment proves that AI increases artists’ creativity.',
  'Researchers used 18 qualitative interviews to explore artists’ creative work.')]


def evaluate(review=review_scope, case_name=None):
    if case_name is not None and case_name not in {row[0] for row in CASES}:
        raise ValueError('Unknown grounding evaluation case')
    failed = []; deadline = time.monotonic() + 1500
    for name, evidence, wrong, correct in CASES:
        if case_name is not None and case_name != name:
            continue
        for label, text, should_pass in [('wrong', wrong, False), ('correct', correct, True)]:
            draft = {'editorial_headline': text, 'editorial_deck': '', 'what_happened': '',
                     'why_it_matters': '', 'for_humans': '', 'for_ai': '', 'limitation': '',
                     'body_paragraphs': [], 'claim_status': 'reporting'}
            passed = False
            attempts = REVIEW_RETRIES if should_pass else 1
            for attempt in range(attempts):
                try:
                    review(draft, [{'source_number': 1, 'evidence': evidence, 'evidence_basis': 'full_source'}], deadline)
                    passed = True
                    break
                except EditorialError as error:
                    if error.code not in {'source_scope_review_failed', 'claim_grounding_failed'}:raise
                    # These fixtures are synthetic and public; diagnostics contain no private sources.
                    print(name + ':' + label + ' attempt ' + str(attempt+1) + ' ' + error.code + ': ' + error.feedback, flush=True)
            if passed != should_pass:failed.append(name + ':' + label)
            print(name + ':' + label + (' PASS' if passed == should_pass else ' FAIL'), flush=True)
    if case_name is not None:
        if failed:raise RuntimeError('Grounding regression failures: ' + ', '.join(failed))
        print('Both live grounding checks passed for ' + case_name + '.', flush=True)
        return
    # Single-field minimal pairs do not exercise the output budget of the real
    # all-fields gate. Include a complete nine-field draft and a body-only error.
    evidence=('Researchers randomly assigned 80 support employees at one company to two groups for four weeks. '
              'Forty employees used an AI writing assistant; forty did not. The assistant group completed support tickets 20 percent faster on average. '
              'Supervisors checked the replies, and the measured error rate did not change. The provider received staff feedback during the trial. '
              'The researchers report that the trial covered one employer and did not measure effects after four weeks. '
              'They did not measure job losses, pay changes, or customer satisfaction.')
    draft={'editorial_headline':'Company trial finds workers finish support tickets faster with AI',
           'editorial_deck':'Researchers randomly assigned support employees at one company to two groups for four weeks.',
           'what_happened':'Researchers randomly assigned 80 support employees at one company to two groups. Forty used an AI writing assistant; forty did not.',
           'why_it_matters':'The assistant group completed support tickets 20 percent faster on average, and the measured error rate did not change.',
           'for_humans':'The assistant group completed support tickets 20 percent faster on average.',
           'for_ai':'The provider received staff feedback during the trial.',
           'limitation':'The trial covered one employer and did not measure effects after four weeks.',
           'body_paragraphs':['The assistant group completed support tickets 20 percent faster on average. Supervisors checked the replies.',
                              'The researchers did not measure job losses, pay changes, or customer satisfaction.'],
           'claim_status':'study'}
    for label,should_pass in [('correct',True),('wrong_body',False)]:
        candidate=copy.deepcopy(draft)
        if not should_pass:candidate['body_paragraphs'][1]='The assistant caused job losses and raised wages across all employers.'
        passed=False
        # A live verifier can falsely reject a supported paraphrase. Confirm a
        # positive failure once before blocking the scheduled research job.
        # Negative fixtures remain strict: one false acceptance fails the gate.
        attempts=REVIEW_RETRIES if should_pass else 1
        for attempt in range(attempts):
            try:
                review(candidate,[{'source_number':1,'evidence':evidence,'evidence_basis':'full_source'}],deadline)
                passed=True
                break
            except EditorialError as error:
                if error.code not in {'source_scope_review_failed','claim_grounding_failed'}:raise
                print('full_draft:'+label+' attempt '+str(attempt+1)+' '+error.code+': '+error.feedback,flush=True)
        if passed!=should_pass:failed.append('full_draft:'+label)
        print('full_draft:'+label+(' PASS' if passed==should_pass else ' FAIL'),flush=True)
    if failed:raise RuntimeError('Grounding regression failures: ' + ', '.join(failed))
    print('All '+str(2*len(CASES)+2)+' live grounding checks passed, including full-draft completion.', flush=True)

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--case', choices=['all']+[row[0] for row in CASES], default='all')
    args=parser.parse_args()
    evaluate(case_name=None if args.case=='all' else args.case)
