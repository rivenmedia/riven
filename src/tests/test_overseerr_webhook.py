import pytest
from program.routers.models.overseerr import OverseerrWebhook

def test_overseerr_webhook_requested_seasons():
    payload = {
        "notification_type": "TEST",
        "event": "TEST_EVENT",
        "subject": "Test",
        "media": {
            "media_type": "tv",
            "tmdbId": 12345,
            "status": "PENDING"
        },
        "extra": [
            {
                "name": "Requested Seasons",
                "value": "1,2,5"
            }
        ]
    }
    
    webhook = OverseerrWebhook(**payload)
    assert webhook.requested_seasons == [1, 2, 5]

def test_overseerr_webhook_requested_seasons_empty():
    payload = {
        "notification_type": "TEST",
        "event": "TEST_EVENT",
        "subject": "Test",
        "media": {
            "media_type": "tv",
            "tmdbId": 12345,
            "status": "PENDING"
        },
        "extra": []
    }
    
    webhook = OverseerrWebhook(**payload)
    assert webhook.requested_seasons is None
