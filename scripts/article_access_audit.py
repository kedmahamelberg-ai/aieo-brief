"""Audit every rendered news/research record for stale access-error copy."""
import re

UNAVAILABLE = re.compile(r'full (?:article|text|paper).{0,45}(?:unavailable|not available|could not|not been|not reviewed)|could not.{0,30}(?:review|read)',re.I)

def audit(rows):
    articles=[x for x in rows if x.get('kind') in {'news','research'}]
    notices=[]
    for row in articles:
        fields=[field for field in ('deck','limitation','for_humans','for_ai') if UNAVAILABLE.search(str(row.get(field) or ''))]
        if fields:
            notices.append({'key':row['key'],'path':row['path'],'fields':fields})
            if row.get('has_editorial') and row.get('evidence_complete'):
                raise ValueError(row['key']+': complete reviewed article still has an unavailable-source notice')
    return {'schema_version':'brief_article_access_audit_v1','articles_checked':len(articles),'access_error_notices':notices,
            'source_link_only':sum(not x.get('has_editorial') for x in articles)}
