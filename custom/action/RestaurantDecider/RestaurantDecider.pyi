"""
RestaurantDecider
"""
from __future__ import annotations
import collections.abc
import typing
__all__: list[str] = ['BUY_ALL', 'BUY_MISSING', 'DecisionResult', 'Dish', 'MenuSolution', 'NO_PURCHASE', 'PurchaseStrategy', 'RestaurantOptimizer']
class DecisionResult:
    strategy: PurchaseStrategy
    def __repr__(self) -> str:
        ...
    @property
    def purchase_plan(self) -> dict[str, int]:
        ...
    @purchase_plan.setter
    def purchase_plan(self, arg0: collections.abc.Mapping[str, typing.SupportsInt | typing.SupportsIndex]) -> None:
        ...
    @property
    def solutions(self) -> list[MenuSolution]:
        ...
    @solutions.setter
    def solutions(self, arg0: collections.abc.Sequence[MenuSolution]) -> None:
        ...
    @property
    def total_profit(self) -> int:
        ...
    @total_profit.setter
    def total_profit(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class Dish:
    cookware: str
    name: str
    def __repr__(self) -> str:
        ...
    @property
    def ingredients(self) -> dict[str, int]:
        ...
    @ingredients.setter
    def ingredients(self, arg0: collections.abc.Mapping[str, typing.SupportsInt | typing.SupportsIndex]) -> None:
        ...
    @property
    def price(self) -> int:
        ...
    @price.setter
    def price(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def profit_rate(self) -> float:
        ...
    @property
    def time(self) -> float:
        ...
    @time.setter
    def time(self, arg0: typing.SupportsFloat | typing.SupportsIndex) -> None:
        ...
    @property
    def unlock_level(self) -> int:
        ...
    @unlock_level.setter
    def unlock_level(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class MenuSolution:
    dish: Dish
    def __repr__(self) -> str:
        ...
    @property
    def bar_ratio(self) -> float:
        ...
    @bar_ratio.setter
    def bar_ratio(self, arg0: typing.SupportsFloat | typing.SupportsIndex) -> None:
        ...
    @property
    def count(self) -> int:
        ...
    @count.setter
    def count(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class PurchaseStrategy:
    """
    Members:
    
      NO_PURCHASE
    
      BUY_ALL
    
      BUY_MISSING
    """
    BUY_ALL: typing.ClassVar[PurchaseStrategy]  # value = <PurchaseStrategy.BUY_ALL: 0>
    BUY_MISSING: typing.ClassVar[PurchaseStrategy]  # value = <PurchaseStrategy.BUY_MISSING: 1>
    NO_PURCHASE: typing.ClassVar[PurchaseStrategy]  # value = <PurchaseStrategy.NO_PURCHASE: 2>
    __members__: typing.ClassVar[dict[str, PurchaseStrategy]]  # value = {'NO_PURCHASE': <PurchaseStrategy.NO_PURCHASE: 2>, 'BUY_ALL': <PurchaseStrategy.BUY_ALL: 0>, 'BUY_MISSING': <PurchaseStrategy.BUY_MISSING: 1>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RestaurantOptimizer:
    def __init__(
            self,
            json_dish: str,
            json_player_status: str,
            warehouse_storage: collections.abc.Mapping[str, typing.SupportsInt | typing.SupportsIndex],
            shop_storage: collections.abc.Mapping[str, typing.SupportsInt | typing.SupportsIndex],
            time_limit: typing.SupportsFloat | typing.SupportsIndex,
            strategy: str,
            purchase_threshold: typing.SupportsInt | typing.SupportsIndex
    ) -> None:
        """
        :param json_dish: dishes.json 的字符串内容
        :param json_player_status: player_status.json 的字符串内容
        :param warehouse_storage: 仓库库存，键为菜品名称，值为库存数量
        :param shop_storage: 商店库存，键为菜品名称，值为库存数量
        :param time_limit: 时间限制，单位为分钟
        :param strategy: 购买策略，可选值为 "BuyAllDemand" | "OnlyBuyDemand" | "DoNotBuy"
        :param purchase_threshold: 购买阈值，当食材仓库储量低于该值时加入购买计划，仅strategy为"OnlyBuyDemand"生效
        """
        ...
    def find_best_solution(self) -> DecisionResult:
        ...
BUY_ALL: PurchaseStrategy  # value = <PurchaseStrategy.BUY_ALL: 0>
BUY_MISSING: PurchaseStrategy  # value = <PurchaseStrategy.BUY_MISSING: 1>
NO_PURCHASE: PurchaseStrategy  # value = <PurchaseStrategy.NO_PURCHASE: 2>
