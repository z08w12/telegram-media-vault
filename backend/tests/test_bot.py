from telegram_media.bot import extract_hashtags


def test_extract_hashtags_supports_chinese_and_deduplicates():
    assert extract_hashtags("旅行记录 #日本 #美食，再来一次 #日本 #video-edit") == ["日本", "美食", "video-edit"]


def test_extract_hashtags_handles_empty_caption():
    assert extract_hashtags(None) == []

