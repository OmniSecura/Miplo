from enum import Enum


class RatingSource(str, Enum):
    MIPLO = "miplo"
    BGG_IMPORT = "bgg_import"


class RatingSort(str, Enum):
    NEWEST = "newest"
    RATING_DESC = "rating_desc"
    RATING_ASC = "rating_asc"


class ReviewReportReason(str, Enum):
    SPAM = "spam"
    OFFENSIVE = "offensive"
    SPOILERS = "spoilers"
    OFF_TOPIC = "off_topic"
