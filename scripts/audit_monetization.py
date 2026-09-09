"""Print the actual configuration, without claiming dashboard approval or income."""
import json
from pathlib import Path
from brief_contract import load_config

ROOT = Path(__file__).resolve().parents[1]


def audit():
    config = load_config(ROOT)
    ads = config['adsense']
    return {
        'ga4_measurement_id': config.get('ga4_measurement_id'),
        'analytics_mode': 'opt_in',
        'ga4_realtime_receipt': 'verify_in_google_analytics',
        'adsense_publisher_id': ads.get('publisher_id'),
        'advertising_enabled': ads.get('enabled', False),
        'google_consent_message_configured': ads.get('cmp_enabled', False),
        'ad_mode': ads.get('mode', 'auto'),
        'banner_slots_configured': [k for k,v in ads.get('slots',{}).items() if v],
        'adsense_site_approval': 'verify_in_adsense_sites',
        'sponsor_campaign_enabled': config.get('sponsor',{}).get('enabled', False),
        'sponsor_enquiries': config.get('revenue',{}).get('contact_url'),
        'reader_payments_configured': bool(config.get('support_url')),
        'paid_or_affiliate_resources_configured': len(config.get('revenue',{}).get('offers',[])),
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
