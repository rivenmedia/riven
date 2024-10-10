from program.settings.compress_json import compress_json, decompress_json

# Example usage
original_data = {
        "profile": "default",
        "require": [],
        "exclude": [],
        "preferred": [],
        "resolutions": {
            "2160p": True,
            "1080p": True,
            "720p": True,
            "480p": False,
            "360p": False,
            "unknown": True
        },
        "options": {
            "title_similarity": 0.85,
            "remove_all_trash": True,
            "remove_ranks_under": -10000,
            "remove_unknown_languages": False,
            "allow_english_in_languages": False
        },
        "languages": {
            "required": [],
            "exclude": [],
            "preferred": []
        },
        "custom_ranks": {
            "quality": {
                "av1": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "avc": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "bluray": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dvd": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hdtv": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hevc": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "mpeg": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "remux": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "vhs": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "web": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "webdl": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "webmux": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "xvid": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                }
            },
            "rips": {
                "bdrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "brrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dvdrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hdrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "ppvrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "satrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "tvrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "uhdrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "vhsrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "webdlrip": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "webrip": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                }
            },
            "hdr": {
                "10bit": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dolby_vision": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hdr": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hdr10plus": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "sdr": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                }
            },
            "audio": {
                "aac": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "ac3": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "atmos": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dolby_digital": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dolby_digital_plus": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dts_lossy": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dts_lossless": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "eac3": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "flac": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "mono": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "mp3": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "stereo": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "surround": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "truehd": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                }
            },
            "extras": {
                "3d": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "converted": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "documentary": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "dubbed": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "edition": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "hardcoded": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "network": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "proper": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "repack": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "retail": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "site": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "subbed": {
                    "fetch": True,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "upscaled": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                }
            },
            "trash": {
                "cam": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "clean_audio": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "pdtv": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "r5": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "screener": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "size": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "telecine": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                },
                "telesync": {
                    "fetch": False,
                    "use_custom_rank": False,
                    "rank": 0
                }
            }
        }
    }


def test_compress_json():
    compressed = compress_json(original_data)
    decompressed = decompress_json(compressed)

    assert original_data == decompressed

# print(f"Original size: {len(json.dumps(original_data))} bytes")
# print(f"Compressed size: {len(compressed)} bytes")
# print(f"Compression ratio: {len(compressed) / len(json.dumps(original_data)):.2f}")
# print(f"Decompressed data matches original: {original_data == decompressed}")

# print(f"Compressed data: {compressed}")