#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <json.hpp>
#include <limits>
#include "assistant.hpp"


class RestaurantOptimizer {
    using json = nlohmann::json;
public:
    double operation_time;  // 运营时间（分钟）
    int purchase_threshold;  // 当仓库储量低于该值时将该食材加入购买计划，仅strategy为BUY_MISSING时生效
    PurchaseStrategy strategy;
    std::unordered_map<std::string, int> levels;
    std::unordered_map<std::string, int> warehouse_storage;
    std::unordered_map<std::string, int> shop_storage;
    std::vector<std::string> all_ingredient_names;
    std::vector<Dish> unlocked_dishes;

private:
    static std::unordered_map<std::string, int> load_levels(const std::string& player_status) {
        using std::unordered_map, std::string;
        return json::parse(player_status)["levels"].get<unordered_map<string, int>>();
    }

    static std::vector<std::string> load_ingredients(const std::string& player_status) {
        using std::vector, std::string;
        return json::parse(player_status)["ingredients"].get<vector<string>>();
    }

    static std::vector<Dish> load_dishes(const std::string& json_dish) {
        using std::vector, std::string, std::unordered_map;
        vector<Dish> result;
        for (const auto& [cookware, dishes] : json::parse(json_dish).items()) {
            for (const auto& dish : dishes) {
                result.emplace_back(
                    dish["dish_id"].get<string>(),
                    static_cast<string>(cookware),
                    dish["profit"].get<int>(),
                    dish["sell_time"].get<double>(),
                    dish["unlock_level"].get<int>(),
                    dish["ingredients"].get<unordered_map<std::string, int>>()
                );
            }
        }
        return result;
    }

    static PurchaseStrategy parse_strategy(const std::string& option)
    noexcept {
        if (option == "BuyAllDemand") {
            return PurchaseStrategy::BUY_ALL;
        }
        if (option == "DoNotBuy") {
            return PurchaseStrategy::NO_PURCHASE;
        }
        return PurchaseStrategy::BUY_MISSING;
    }

public:
    explicit RestaurantOptimizer(
        const std::string& json_dish,
        const std::string& json_player_status,
        std::unordered_map<std::string, int> warehouse_storage,
        std::unordered_map<std::string, int> shop_storage,
        const double time_limit,
        const std::string& strategy,
        const int purchase_threshold
    ) :
        operation_time(time_limit > 0 ? time_limit * 60.0 : DEFAULT_OPERATION_TIME),
        purchase_threshold(purchase_threshold),
        strategy(parse_strategy(strategy)),
        levels(std::move(load_levels(json_player_status))),
        warehouse_storage(std::move(warehouse_storage)),
        shop_storage(std::move(shop_storage)),
        all_ingredient_names(std::move(load_ingredients(json_player_status)))
    {
        for (const auto& dish: load_dishes(json_dish)) {
            if (dish.unlock_level <= map_get(levels, dish.cookware, 0)) {
                this->unlocked_dishes.push_back(dish);
            }
        }
    }

private:
    // ── 食材可用量计算 ──────────────────────────────────────────

    /*
    根据购买的食材集合构建可用食材。
    bought_set 中的食材 = 仓库 + 商店量；其余 = 仓库量。
    */
    [[nodiscard]]
    std::unordered_map<std::string, int> build_available(const std::unordered_set<std::string>& bought_set)
    const {
        using std::unordered_map, std::string;
        unordered_map<string, int> available;
        for (const auto& name: all_ingredient_names) {
            const int base = map_get(warehouse_storage, name, 0);
            if (bought_set.contains(name)) {
                available[name] = base + map_get(shop_storage, name, 0);
            } else {
                available[name] = base;
            }
        }
        return available;
    }

    /*
    获取与给定菜品组合相关的、商店中有售的食材列表。
    只有菜品确实需要的食材才考虑购买。
    */
    [[nodiscard]]
    std::vector<std::string> get_relevant_shop_ingredients(const std::vector<Dish>& dishes)
    const {
        using std::unordered_set, std::string;
        unordered_set<string> needed;
        for (const auto& dish: dishes) {
            for (const auto& ingredient: dish.ingredients | std::views::keys) {
                if (shop_storage.contains(ingredient)) {
                    needed.insert(ingredient);
                }
            }
        }
        return {needed.begin(), needed.end()};
    }

    // ── 菜品可制作量计算 ──────────────────────────────────────

    /*综合时间和食材限制计算最大可制作数量*/
    [[nodiscard]]
    int calc_max_count(const Dish& dish, const std::unordered_map<std::string, int>& available)
    const {
        using std::min, std::numeric_limits;
        // 时间限制
        int time_limit = 0;
        if (dish.time > 0) {
            time_limit = static_cast<int>(
                static_cast<double>(operation_time) / dish.time
            );
        }

        // 食材限制
        int ingredients_limit = numeric_limits<int>::max();
        for (const auto& [ingredient, required]: dish.ingredients) {
            if (required > 0) {
                const int amount = map_get(available, ingredient, 0);
                ingredients_limit = min(ingredients_limit, amount / required);
            }
        }
        ingredients_limit = ingredients_limit != numeric_limits<int>::max() ? ingredients_limit : 0;
        return min(time_limit, ingredients_limit);
    }

    // ── 进度条比例计算 ────────────────────────────────────────

    /*
    根据菜品、制作数量及当前可用食材，
    计算进度条拖动比例（三位小数）和制作后的剩余食材（通过引用current更新）。
    进度条终点 = 短板食材决定的最大可制作数量
    比例 = count / 最大可制作数量
    */
    [[nodiscard]]
    static double calc_bar_ratio(
        const Dish& dish,
        const int count,
        std::unordered_map<std::string, int>& current
        ) {
        if (count == 0) return 0.0;

        using std::min, std::max, std::numeric_limits;
        // 计算基于当前可用食材的最大可制作数量（短板）
        int max_makeable = numeric_limits<int>::max();
        for (const auto& [ingredient, required]: dish.ingredients) {
            if (required < 1) continue;
            const int amount = map_get(current, ingredient, 0);
            max_makeable = min(max_makeable, amount / required);
        }
        if (max_makeable == numeric_limits<int>::max() || max_makeable < 1) {
            return 0.0;
        }

        // 比例 = 需要的数量 / 最大可制作数量，截断到三位小数
        const double ratio = min(
                std::floor(static_cast<double>(count) / max_makeable * 1000.0) / 1000.0,
                1.0
            );

        // 扣除食材
        for (const auto& [ingredient, required]: dish.ingredients) {
            if (required < 1) continue;
            current[ingredient] = max(0, map_get(current, ingredient, 0) - required * count);
        }

        return ratio;
    }

    // ── 菜品枚举 ────────────────────────────────────────────

    /*在给定可用食材下，单菜品的最优数量和收益。array的两个元素分别为数量和收益*/
    [[nodiscard]]
    PurchaseCombo evaluate_single(const Dish& dish, const std::unordered_map<std::string, int>& available)
    const {
        const int count = calc_max_count(dish, available);
        return  {{count}, dish.price * count};
    }

    /*
    在给定可用食材下，两个菜品的最优数量组合。
    两菜品并行，食材共享，精确枚举。
    考虑到任务对速度要求低、对精度要求高，因此完整枚举。
    */
    [[nodiscard]]
    PurchaseCombo evaluate_two_dishes(
        const Dish& dish1,
        const Dish& dish2,
        const std::unordered_map<std::string, int>& available
        )
    const {
        using std::move, std::vector;
        vector best_counts = {0, 0};
        int best_profit = 0;

        const int limit1 = calc_max_count(dish1, available);
        for (int count1 = 0; count1 <= limit1; ++count1) {
            // 计算dish1在制作count1份后的剩余食材
            bool feasible = true;
            auto remaining = available;
            for (const auto& [ingredient, required]: dish1.ingredients) {
                if (required < 1) continue;
                remaining[ingredient] = map_get(remaining, ingredient, 0) - required * count1;
                if (remaining[ingredient] < 0) {
                    // count1已超出食材限制
                    feasible = false;
                    break;
                }
            }
            if (!feasible) break;

            // dish2在剩余食材下的最大数量
            const int count2 = calc_max_count(dish2, remaining);
            if (
                const int profit = count1 * dish1.price + count2 * dish2.price;
                profit > best_profit
                ) {
                best_profit = profit;
                best_counts = {count1, count2};
            }
        }
        return {move(best_counts), best_profit};
    }

    /*枚举购买子集，单菜品*/
    [[nodiscard]]
    PurchaseCombo enumerate_subsets_single(const Dish& dish)
    const {
        using std::unordered_set, std::move, std::string;
        unordered_set<string> best_bought;
        int best_count = 0;
        int best_profit = 0;

        // 枚举所有子集：从空集到全集
        const auto&& relevant_shop_ingredients = get_relevant_shop_ingredients({dish});
        const int relevant_num = static_cast<int>(relevant_shop_ingredients.size());
        for (int mask = 0 ; mask < (1 << relevant_num) ; ++mask) {
            unordered_set<string> bought;
            for (int idx = 0 ; idx < relevant_num ; ++idx) {
                if (mask & (1 << idx)) {
                    bought.insert(relevant_shop_ingredients[idx]);
                }
            }
            if (
                const auto current_combo = evaluate_single(dish, build_available(bought));
                current_combo.total_profit > best_profit
                ) {
                best_profit = current_combo.total_profit;
                best_count = current_combo.purchase_counts[0];
                best_bought = move(bought);
            }
        }
        return {move(best_bought), {best_count}, best_profit};
    }

    /*枚举购买子集，双菜品*/
    [[nodiscard]]
    PurchaseCombo enumerate_subsets_two(const Dish& dish1, const Dish& dish2)
    const {
        using std::unordered_set, std::move, std::string, std::vector;
        unordered_set<string> best_bought;
        vector best_counts = {0, 0};
        int best_profit = 0;

        // 枚举所有子集：从空集到全集
        const auto&& relevant_shop_ingredients = get_relevant_shop_ingredients(
            {dish1, dish2}
            );
        const int relevant_num = static_cast<int>(relevant_shop_ingredients.size());
        for (int mask = 0 ; mask < (1 << relevant_num) ; ++mask) {
            unordered_set<string> bought;
            for (int idx = 0 ; idx < relevant_num ; ++idx) {
                if (mask & (1 << idx)) {
                    bought.insert(relevant_shop_ingredients[idx]);
                }
            }
            if (
                const auto&& current_combo = evaluate_two_dishes(dish1, dish2, build_available(bought));
                current_combo.total_profit > best_profit
                ) {
                best_profit = current_combo.total_profit;
                best_counts = current_combo.purchase_counts;
                best_bought = move(bought);
            }
        }
        return {move(best_bought), move(best_counts), best_profit};
    }

    // ── 主求解 ────────────────────────────────────────────────

    /*可用食材固定时的求解（NO_PURCHASE / BUY_ALL）*/
    [[nodiscard]]
    DecisionResult solve_fixed(const std::unordered_set<std::string>& bought_set)
    const {
        using std::vector, std::move, std::unordered_set, std::string;
        const auto&& available = build_available(bought_set);
        vector<Dish> best_dishes;
        vector<int> best_counts;
        int best_profit = 0;

        for (const auto& dish : unlocked_dishes) {
            if (
                auto&& evaluations = evaluate_single(dish, available);
                evaluations.total_profit > best_profit
                ) {
                best_profit = evaluations.total_profit;
                best_dishes = {dish};
                best_counts = move(evaluations.purchase_counts);
            }
        }

        for (const auto& dishes : combinations(unlocked_dishes, 2)) {
            if (
                auto&& evaluations = evaluate_two_dishes(dishes[0], dishes[1], available);
                evaluations.total_profit > best_profit
                ) {
                best_profit = evaluations.total_profit;
                best_dishes = dishes;
                best_counts = move(evaluations.purchase_counts);
            }
        }

        if (strategy == PurchaseStrategy::NO_PURCHASE) {
            return build_result(best_dishes, best_counts, best_profit, bought_set);
        }

        unordered_set<string> demand_ingredients;
        for (const auto& dish: best_dishes) {
            for (const auto& ingredient : dish.ingredients | std::views::keys) {
                demand_ingredients.insert(ingredient);
            }
        }
        return build_result(best_dishes, best_counts, best_profit, demand_ingredients);
    }

    /*
    BUY_MISSING 策略：只购买「能提升收益」的食材。

    语义：对于最终选定的菜品组合，如果某种食材的总需求超出仓库存量，
    才从商店购买（买满商店限购量）。

    实现：对每个候选菜品组合，枚举相关商店食材的购买子集，
    计算每种购买方案下的最优收益，取全局最优。

    优化：商店食材中只考虑该组合实际需要的食材，
    且通常相关食材种类不多（游戏场景），子集枚举可行。
    */
    [[nodiscard]]
    DecisionResult solve_buy_missing()
    const {
        using std::vector, std::unordered_set, std::string, std::move;
        unordered_set<string> best_bought;
        vector<Dish> best_dishes;
        vector<int> best_counts;
        int best_profit = 0;

        // 单菜品
        for (const auto& dish : unlocked_dishes) {
            if (
                auto&& current_combo = enumerate_subsets_single(dish);
                current_combo.total_profit > best_profit
                ) {
                best_profit = current_combo.total_profit;
                best_dishes = {dish};
                best_counts = move(current_combo.purchase_counts);
                best_bought = move(current_combo.purchase_targets);
            }
        }

        // 双菜品
        for (const auto& dishes : combinations(unlocked_dishes, 2)) {
            if (
                auto&& current_combo = enumerate_subsets_two(dishes[0], dishes[1]);
                current_combo.total_profit > best_profit
                ) {
                best_profit = current_combo.total_profit;
                best_dishes = dishes;
                best_counts = move(current_combo.purchase_counts);
                best_bought = move(current_combo.purchase_targets);
            }
        }

        // 在需要额外补货时合并 filter 结果
        if (purchase_threshold > 0) {
            auto&& extra =  // 验证购买合理性：最终方案中，只保留需求确实超出仓库的食材
                filter_actually_missing(best_dishes, best_counts);
            best_bought.merge(extra);
        }
        return build_result(best_dishes, best_counts, best_profit, best_bought);
    }

    /*
    最终校验：
    对选定菜品的所有食材，若制作后仓库剩余量低于 purchase_threshold 且商店有售则购买。
    threshold=0 时退化为仅购买需求超出仓库的食材。
    */
    [[nodiscard]]
    std::unordered_set<std::string> filter_actually_missing(
        const std::vector<Dish>& dishes,
        const std::vector<int>& counts
    )
    const {
        using std::unordered_set, std::unordered_map, std::string, std::views::zip;

        unordered_map<string, int> total_demand;
        for (const auto& [dish, count]: zip(dishes, counts)) {
            for (const auto& [ingredient, required]: dish.ingredients) {
                total_demand[ingredient] = map_get(total_demand, ingredient, 0) + required * count;
            }
        }

        unordered_set<string> should_buy;
        for (const auto& [name, demand]: total_demand) {
            if (!(shop_storage.contains(name))) continue;  // 今日商店不销售该食材
            if (map_get(warehouse_storage, name, 0) - demand < purchase_threshold) {
                should_buy.insert(name);
            }
        }

        return should_buy;
    }

    /*构建结果*/
    [[nodiscard]]
    DecisionResult build_result(
        const std::vector<Dish>& dishes,
        const std::vector<int>& counts,
        const int total_profit,
        const std::unordered_set<std::string>& bought_set
    )
    const {
        using std::move, std::unordered_map, std::vector, std::string, std::views::zip;
        auto&& current = build_available(bought_set);
        vector<MenuSolution> solutions;

        for (const auto& [dish, count]: zip(dishes, counts)) {
            double bar_ratio = calc_bar_ratio(dish, count, current);
            solutions.emplace_back(dish, count, bar_ratio);
        }

        // 购买计划：bought_set 中的食材，购买量 = 商店限购量
        unordered_map<string, int> purchase_plan;
        for (const auto& ingredient: bought_set) {
            if (
                const int shop_amount = map_get(shop_storage, ingredient, 0);
                shop_amount > 0
                ) {
                purchase_plan[ingredient] = shop_amount;
            }
        }

        return DecisionResult{
            solutions,
            purchase_plan,
            total_profit,
            strategy
        };
    }

public:
    // ── 求解接口 ───────────────────────────────────────────────
    /*
    找到最优菜品组合方案。
    根据购买策略的不同：
    - NO_PURCHASE / BUY_ALL: 可用食材是确定的，直接求解。
    - BUY_MISSING: 可用食材取决于选哪些菜品（因为只买缺少的食材），
    需要对每个候选组合单独计算可用食材。
    */
    [[nodiscard]]
    DecisionResult find_best_solution()
    const {
        using namespace std;
        switch (strategy) {
            case PurchaseStrategy::NO_PURCHASE:
                return solve_fixed({});
            case PurchaseStrategy::BUY_ALL:
                return solve_fixed(ranges::to<unordered_set<string>>(shop_storage | views::keys));
            default:
                return solve_buy_missing();
        }
    }
};


namespace py = pybind11;
PYBIND11_MODULE(RestaurantDecider, mod) {
    mod.doc() = "RestaurantDecider";
    using std::to_string, std::format, std::string;

    py::enum_<PurchaseStrategy>(mod, "PurchaseStrategy")
        .value("NO_PURCHASE", PurchaseStrategy::NO_PURCHASE)
        .value("BUY_ALL", PurchaseStrategy::BUY_ALL)
        .value("BUY_MISSING", PurchaseStrategy::BUY_MISSING)
        .export_values();

    py::class_<Dish>(mod, "Dish")
        .def_readwrite("name", &Dish::name)
        .def_readwrite("cookware", &Dish::cookware)
        .def_readwrite("price", &Dish::price)
        .def_readwrite("time", &Dish::time)
        .def_readonly("profit_rate", &Dish::profit_rate)
        .def_readwrite("unlock_level", &Dish::unlock_level)
        .def_readwrite("ingredients", &Dish::ingredients)
        .def("__repr__", [](const Dish& dish) {return dish.response();});

    py::class_<MenuSolution>(mod, "MenuSolution")
        .def_readwrite("dish", &MenuSolution::dish)
        .def_readwrite("count", &MenuSolution::count)
        .def_readwrite("bar_ratio", &MenuSolution::bar_ratio)
        .def("__repr__", [](const MenuSolution& sol) {return sol.response();});

    py::class_<DecisionResult>(mod, "DecisionResult")
        .def_readwrite("solutions", &DecisionResult::solutions)
        .def_readwrite("purchase_plan", &DecisionResult::purchase_plan)
        .def_readwrite("total_profit", &DecisionResult::total_profit)
        .def_readwrite("strategy", &DecisionResult::strategy)
        .def("__repr__", [](const DecisionResult& res) {return res.response();});

    py::class_<RestaurantOptimizer>(mod, "RestaurantOptimizer")
        .def(py::init<
                const std::string&,
                const std::string&,
                std::unordered_map<std::string, int>,
                std::unordered_map<std::string, int>,
                const double,
                const std::string&,
                const int
            >(),
            py::arg("json_dish"),
            py::arg("json_player_status"),
            py::arg("warehouse_storage"),
            py::arg("shop_storage"),
            py::arg("time_limit"),
            py::arg("strategy"),
            py::arg("purchase_threshold")
            )
        .def("find_best_solution", &RestaurantOptimizer::find_best_solution);
}
