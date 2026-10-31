"""One module per page. Each defines TITLE, ICON and build(params) -> {"hero", "controls", "sections"}.

To add a page: create a module here and add it to PAGES. The navigation follows this order.
"""
from web.pages import backtest_page, exposure, overview, returns

PAGES = {
    "overview": overview,
    "returns": returns,
    "exposure": exposure,
    "backtest": backtest_page,
}
