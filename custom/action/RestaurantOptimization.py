from typing import List, Dict, Tuple, Literal, FrozenSet, Set
from itertools import combinations
from dataclasses import dataclass
from enum import Enum
import os
import json
import math


# ── 基本参数 ──────────────────────────────────────────────
DEFAULT_OPERATION_TIME = 26 * 60


class PurchaseStrategy(Enum):
    """购买策略"""
    BUY_ALL = "buy_all"           # 买满需求食材
    BUY_MISSING = "buy_missing"   # 购买缺少食材
    NO_PURCHASE = "no_purchase"   # 不购买食材


@dataclass
class Dish:
    """菜品类"""
    name: str
    cookware: Literal["炒锅", "烤箱", "蒸笼", "煮锅"]
    price: int
    time: float  # 预计售卖时间（分钟）
    unlock_level: int
    ingredients: Dict[str, int]

    @property
    def profit_rate(self) -> float:
        """收益率（每分钟收益）"""
        return self.price / self.time if self.time > 0 else 0

    def __repr__(self):
        return f"{self.name}(¥{self.price}/{self.time}min, 收益率:{self.profit_rate:.2f})"


@dataclass
class MenuSolution:
    """单个菜品的上架方案"""
    dish: Dish
    count: int
    bar_ratio: float  # 三位小数

    def __repr__(self):
        return (f"上架 {self.dish.name} {self.count}份, "
                f"进度条比例 {self.bar_ratio:.3f}, "
                f"预计收益 {self.count * self.dish.price}, "
                f"预计耗时 {self.count * self.dish.time / 60:.1f}h")


@dataclass
class OptimizationResult:
    """完整的优化结果"""
    solutions: List[MenuSolution]
    purchase_plan: Dict[str, int]  # 需要在商店购买的食材及数量
    total_profit: int
    strategy: PurchaseStrategy

    def __repr__(self):
        lines = [f"策略: {self.strategy.value}", f"总预计收益: {self.total_profit}"]
        for s in self.solutions:
            lines.append(f"  {s}")
        if self.purchase_plan:
            lines.append("需购买食材:")
            for name, amount in self.purchase_plan.items():
                if amount > 0:
                    lines.append(f"  {name}: {amount}")
        return "\n".join(lines)


class RestaurantOptimizer:
    def __init__(
        self,
        data_path: str,
        warehouse_storage: Dict[str, int],
        shop_storage: Dict[str, int],
        time_limit: float,
        strategy: PurchaseStrategy = PurchaseStrategy.BUY_MISSING,
    ):
        """
        :param data_path: 餐厅相关文件的存储路径（绝对路径）
        :param warehouse_storage: 仓库食材储量
        :param shop_storage: 商店中可购买的食材（食材名 -> 可购买数量）
        :param time_limit: 上架菜品预计的售卖时间（小时）
        :param strategy: 购买策略
        """
        self.data_path = data_path
        self.time_limit_minutes = int(time_limit * 60) \
            if isinstance(time_limit, (int, float)) else DEFAULT_OPERATION_TIME
        self.warehouse_storage = warehouse_storage.copy()
        self.shop_storage = shop_storage.copy()
        self.strategy = strategy

        levels, self.all_ingredient_names = self._load_levels_and_ingredients()
        all_dishes = self._load_dishes()
        self.unlocked_dishes = [
            d for d in all_dishes if d.unlock_level <= levels.get(d.cookware, 0)
        ]

    # ── 数据加载 ──────────────────────────────────────────────
    def _load_dishes(self) -> List[Dish]:
        dishes: List[Dish] = []
        path = os.path.join(self.data_path, "dishes.json")
        with open(path, "r", encoding="UTF-8") as f:
            dic_dishes = json.load(f)
        for cookware, cookware_dishes in dic_dishes.items():
            for d in cookware_dishes:
                dishes.append(Dish(
                    name=d["dish_id"],
                    cookware=cookware,
                    price=d.get("profit", 0),
                    time=d.get("sell_time", 0),
                    unlock_level=d.get("unlock_level", 3),
                    ingredients=d.get("ingredients", {}),
                ))
        return dishes

    def _load_levels_and_ingredients(self) -> Tuple[Dict[str, int], List[str]]:
        path = os.path.join(self.data_path, "player_status.json")
        with open(path, "r", encoding="UTF-8") as f:
            ps = json.load(f)
        return ps["levels"], ps["ingredients"]

    # ── 食材可用量计算 ──────────────────────────────────────────
    def _build_available(self, bought_set: FrozenSet[str]) -> Dict[str, int]:
        """
        根据购买的食材集合构建可用食材。
        bought_set 中的食材 = 仓库 + 商店量；其余 = 仓库量。
        """
        available = {}
        for name in self.all_ingredient_names:
            base = self.warehouse_storage.get(name, 0)
            if name in bought_set:
                available[name] = base + self.shop_storage.get(name, 0)
            else:
                available[name] = base
        return available

    def _get_relevant_shop_ingredients(self, dishes: List[Dish]) -> List[str]:
        """
        获取与给定菜品组合相关的、商店中有售的食材列表。
        只有菜品确实需要的食材才考虑购买。
        """
        needed: Set[str] = set()
        for dish in dishes:
            for ing in dish.ingredients:
                if ing in self.shop_storage:
                    needed.add(ing)
        return list(needed)

    # ── 菜品可制作量计算 ──────────────────────────────────────
    def _calc_max_count(self, dish: Dish, available: Dict[str, int]) -> int:
        """综合时间和食材限制计算最大可制作数量"""
        # 时间限制
        if dish.time <= 0:
            time_limit = 0
        else:
            time_limit = int(self.time_limit_minutes / dish.time)

        # 食材限制
        max_count_by_ingredients = float("inf")
        for ing, required in dish.ingredients.items():
            if required > 0:
                amt = available.get(ing, 0)
                max_count_by_ingredients = min(max_count_by_ingredients, amt // required)
        ingredients_limit = int(max_count_by_ingredients) if max_count_by_ingredients != float("inf") else 0

        return min(time_limit, ingredients_limit)

    # ── 进度条比例计算 ────────────────────────────────────────
    @staticmethod
    def _calc_bar_ratio(
            dish: Dish,
            count: int,
            available_ingredients: Dict[str, int],
    ) -> Tuple[float, Dict[str, int]]:
        """
        根据菜品、制作数量及当前可用食材，
        计算进度条拖动比例（三位小数）和制作后的剩余食材。

        进度条终点 = 短板食材决定的最大可制作数量
        比例 = count / 最大可制作数量
        """
        remaining = available_ingredients.copy()
        if count == 0:
            return 0.0, remaining

        # 计算基于当前可用食材的最大可制作数量（短板）
        max_makeable = float("inf")
        for ing, required in dish.ingredients.items():
            if required <= 0:
                continue
            amt = remaining.get(ing, 0)
            max_makeable = min(max_makeable, amt // required)

        if max_makeable == float("inf") or max_makeable <= 0:
            # 没有任何食材需求或食材为0，无法制作
            return 0.0, remaining

        # 比例 = 需要的数量 / 最大可制作数量，截断到三位小数
        # 使用 math.floor 来截断到三位（避免 round 可能的四舍五入导致超出1.0）
        ratio = min(
                math.floor(count / max_makeable * 1000) / 1000,
                1.0
        )

        # 扣除食材
        for ing, required in dish.ingredients.items():
            if required <= 0:
                continue
            remaining[ing] = max(0, remaining.get(ing, 0) - required * count)

        return ratio, remaining

    # ── 菜品枚举 ────────────────────────────────────────────
    def _evaluate_single(
            self,
            dish: Dish,
            available: Dict[str, int]
    ) -> Tuple[int, int]:
        """在给定可用食材下，单菜品的最优数量和收益"""
        count = self._calc_max_count(dish, available)
        return count, count * dish.price

    def _evaluate_two_dishes(
            self,
            dish1: Dish,
            dish2: Dish,
            available: Dict[str, int],
    ) -> Tuple[List[int], int]:
        """
        在给定可用食材下，两个菜品的最优数量组合。
        两菜品并行，食材共享，精确枚举。
        考虑到任务对速度要求低、对精度要求高，因此完整枚举。
        """
        best_counts = [0, 0]
        best_profit = 0

        limit1 = self._calc_max_count(dish1, available)
        for count1 in range(limit1 + 1):
            # 计算菜品1在制作count1份后的剩余食材
            remaining = available.copy()
            feasible = True
            for ingredient, required in dish1.ingredients.items():
                if required <= 0:
                    continue
                remaining[ingredient] = remaining.get(ingredient, 0) - required * count1
                if remaining[ingredient] < 0:
                    # count1已超出食材限制
                    feasible = False
                    break

            if not feasible:
                break

            # 菜品2在剩余食材下的最大数量
            count2 = self._calc_max_count(dish2, remaining)
            profit = count1 * dish1.price + count2 * dish2.price
            if profit > best_profit:
                best_profit = profit
                best_counts = [count1, count2]

        return best_counts, best_profit

    # ── 主求解 ────────────────────────────────────────────────
    def find_best_solution(self) -> OptimizationResult:
        """
        找到最优菜品组合方案。

        根据购买策略的不同：
        - NO_PURCHASE / BUY_ALL: 可用食材是确定的，直接求解。
        - BUY_MISSING: 可用食材取决于选哪些菜品（因为只买缺少的食材），
          需要对每个候选组合单独计算可用食材。
        """
        if self.strategy == PurchaseStrategy.NO_PURCHASE:
            return self._solve_fixed(frozenset())
        elif self.strategy == PurchaseStrategy.BUY_ALL:
            return self._solve_fixed(frozenset(self.shop_storage.keys()))
        else:  # BUY_MISSING
            return self._solve_buy_missing()

    '''针对固定食材'''
    def _solve_fixed(self, bought_set: FrozenSet[str]) -> OptimizationResult:
        """可用食材固定时的求解（NO_PURCHASE / BUY_ALL）"""
        available = self._build_available(bought_set)

        best_dishes: List[Dish] = []
        best_counts: List[int] = []
        best_profit: int = 0

        for dish in self.unlocked_dishes:
            count, profit = self._evaluate_single(dish, available)
            if profit > best_profit:
                best_profit = profit
                best_dishes = [dish]
                best_counts = [count]

        for d1, d2 in combinations(self.unlocked_dishes, 2):
            counts, profit = self._evaluate_two_dishes(d1, d2, available)
            if profit > best_profit:
                best_profit = profit
                best_dishes = [d1, d2]
                best_counts = counts

        demand_ingredients = []
        for dish in best_dishes:
            demand_ingredients += list(dish.ingredients.keys())

        return self._build_result(best_dishes, best_counts, best_profit, frozenset(demand_ingredients))

    '''针对BUY_MISSING'''
    def _solve_buy_missing(self) -> OptimizationResult:
        """
        BUY_MISSING 策略：只购买「能提升收益」的食材。

        语义：对于最终选定的菜品组合，如果某种食材的总需求超出仓库存量，
        才从商店购买（买满商店限购量）。

        实现：对每个候选菜品组合，枚举相关商店食材的购买子集，
        计算每种购买方案下的最优收益，取全局最优。

        优化：商店食材中只考虑该组合实际需要的食材，
        且通常相关食材种类不多（游戏场景），子集枚举可行。
        """
        best_dishes: List[Dish] = []
        best_counts: List[int] = []
        best_profit: int = 0
        best_bought: FrozenSet[str] = frozenset()

        # 单菜品
        for dish in self.unlocked_dishes:
            dishes_list = [dish]
            bought, counts, profit = self._enumerate_subsets_single(dish)
            if profit > best_profit:
                best_profit = profit
                best_dishes = dishes_list
                best_counts = counts
                best_bought = bought

        # 双菜品
        for d1, d2 in combinations(self.unlocked_dishes, 2):
            bought, counts, profit = self._enumerate_subsets_two(d1, d2)
            if profit > best_profit:
                best_profit = profit
                best_dishes = [d1, d2]
                best_counts = counts
                best_bought = bought

        # 验证购买合理性：最终方案中，只保留需求确实超出仓库的食材
        final_bought = self._filter_actually_missing(
            best_dishes, best_counts, best_bought
        )
        return self._build_result(best_dishes, best_counts, best_profit, final_bought)

    def _enumerate_subsets_single(self, dish: Dish) -> Tuple[FrozenSet[str], List[int], int]:
        """枚举购买子集，单菜品"""
        best_bought: FrozenSet[str] = frozenset()
        best_count = 0
        best_profit = 0

        # 枚举所有子集：从空集到全集
        relevant_shop_ings = self._get_relevant_shop_ingredients([dish])
        n = len(relevant_shop_ings)
        for mask in range(1 << n):
            bought = frozenset(
                relevant_shop_ings[i] for i in range(n) if mask & (1 << i)
            )
            available = self._build_available(bought)
            count, profit = self._evaluate_single(dish, available)

            if profit > best_profit:
                best_profit = profit
                best_count = count
                best_bought = bought

        return best_bought, [best_count], best_profit

    def _enumerate_subsets_two(
            self,
            d1: Dish,
            d2: Dish
    ) -> Tuple[FrozenSet[str], List[int], int]:
        """枚举购买子集，双菜品"""
        best_bought: FrozenSet[str] = frozenset()
        best_counts = [0, 0]
        best_profit = 0

        relevant_shop_ings = self._get_relevant_shop_ingredients([d1, d2])
        n = len(relevant_shop_ings)
        for mask in range(1 << n):
            bought = frozenset(
                relevant_shop_ings[i] for i in range(n) if mask & (1 << i)
            )
            available = self._build_available(bought)
            counts, profit = self._evaluate_two_dishes(d1, d2, available)

            if profit > best_profit:
                best_profit = profit
                best_counts = counts
                best_bought = bought

        return best_bought, best_counts, best_profit

    def _filter_actually_missing(
            self,
            dishes: List[Dish],
            counts: List[int],
            bought: FrozenSet[str],
    ) -> FrozenSet[str]:
        """
        最终校验：在最终方案中，只保留总需求确实超出仓库存量的食材购买。
        如果某食材买了但实际需求没超仓库，就去掉（不影响count，因为仓库就够了）。
        """
        total_demand: Dict[str, int] = {}
        for dish, count in zip(dishes, counts):
            for ing, req in dish.ingredients.items():
                total_demand[ing] = total_demand.get(ing, 0) + req * count

        actually_missing: Set[str] = set()
        for ing_name in bought:
            demand = total_demand.get(ing_name, 0)
            warehouse_amt = self.warehouse_storage.get(ing_name, 0)
            if demand > warehouse_amt:
                actually_missing.add(ing_name)

        return frozenset(actually_missing)

    # ── 构建结果 ──────────────────────────────────────────────
    def _build_result(
        self,
        dishes: List[Dish],
        counts: List[int],
        total_profit: int,
        bought_set: FrozenSet[str],
    ) -> OptimizationResult:
        """构建最终结果，用实际可用食材计算进度条比例"""
        available = self._build_available(bought_set)
        solutions: List[MenuSolution] = []
        remaining = available.copy()

        for dish, count in zip(dishes, counts):
            ratio, remaining = self._calc_bar_ratio(dish, count, remaining)
            solutions.append(MenuSolution(
                dish=dish,
                count=count,
                bar_ratio=ratio,
            ))

        # 购买计划：bought_set 中的食材，购买量 = 商店限购量
        purchase_plan: Dict[str, int] = {}
        for ing_name in bought_set:
            shop_amt = self.shop_storage.get(ing_name, 0)
            if shop_amt > 0:
                purchase_plan[ing_name] = shop_amt

        return OptimizationResult(
            solutions=solutions,
            purchase_plan=purchase_plan,
            total_profit=total_profit,
            strategy=self.strategy
        )
