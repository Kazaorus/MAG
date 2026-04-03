#pragma once
#include <string>
#include <string_view>
#include <stdexcept>
#include <utility>
#include <vector>
#include <algorithm>
#include <generator>
#include <format>


// 默认运营时间：32小时
inline int DEFAULT_OPERATION_TIME = 32 * 60;


// 购买策略
enum class PurchaseStrategy {
    BUY_ALL,
    BUY_MISSING,
    NO_PURCHASE
};


// 返回所有组合
template<typename T>
[[nodiscard]]
std::generator<std::vector<T>> combinations(const std::vector<T>& items, size_t k) {
    using std::vector;
    vector<vector<T>> result;
    if (k > items.size()) co_return;
    if (k == 0) {
        // 显式处理 C(n,0) = 1 的情况
        co_yield vector<T>{};
        co_return;
    }

    // 创建掩码：前 k 个为 true (1)，后面为 false (0)
    // 使用 vector<char> 避免 vector<bool> 的代理引用问题
    vector<char> mask(items.size(), 0);
    std::fill_n(mask.begin(), k, 1);

    do {
        vector<T> current_combo;
        current_combo.reserve(k);
        for (size_t idx=0; idx < items.size(); ++idx) {
            if (mask[idx]) {
                current_combo.push_back(items[idx]);
            }
        }
        co_yield current_combo;
    } while (std::ranges::prev_permutation(mask).found);
}


// 从映射中获取值，若不存在则返回默认值
template<typename T>
[[nodiscard]]
T map_get(const std::unordered_map<std::string, T>& map, const std::string& key, const T default_value) {
    if (auto it = map.find(key); it != map.end()) {
        return it->second;
    }
    return default_value;
}


struct Bar {
    double ratio;
    std::unordered_map<std::string, int> remaining_ingredients;

    Bar(const double ratio, std::unordered_map<std::string, int> remaining_ingredients) :
        ratio(ratio),
        remaining_ingredients(std::move(remaining_ingredients))
    {}
};


struct PurchaseCombo {
    std::unordered_set<std::string> purchase_targets;
    std::vector<int>  purchase_counts;
    int total_profit;

    PurchaseCombo(
            std::unordered_set<std::string> purchase_targets,
            std::vector<int> purchase_counts,
            const int total_profit
        ) :
        purchase_targets(std::move(purchase_targets)),
        purchase_counts(std::move(purchase_counts)),
        total_profit(total_profit)
        {}

    PurchaseCombo(
            std::vector<int> purchase_counts,
            const int total_profit
        ) :
        purchase_targets(std::unordered_set<std::string>()),
        purchase_counts(std::move(purchase_counts)),
        total_profit(total_profit)
        {}
};


struct Dish {
    std::string name;
    std::string cookware;
    int price;
    double time;  //预计售卖时间（分钟）
    double profit_rate;
    int unlock_level;
    std::unordered_map<std::string, int> ingredients;

    explicit Dish(
            std::string name,
            const std::string_view cookware,
            const int price,
            const double time,
            const int unlock_level,
            std::unordered_map<std::string, int> ingredients
        ) :
        name(std::move(name)),
        cookware(valid_cookware(cookware)),
        price(price),
        time(time),
        profit_rate(time > 0 ? static_cast<double>(price) / time : 0),
        unlock_level(unlock_level),
        ingredients(std::move(ingredients))
        {}

    // 厨具检查：正确则返回原值，否则抛出异常
    [[nodiscard]]
    static std::string valid_cookware(const std::string_view cookware) {
        if (cookware == "炒锅" || cookware == "烤箱" ||
            cookware == "蒸笼" || cookware == "煮锅") {
            return std::string(cookware);
            }
        throw std::invalid_argument("无效的厨具: " + std::string(cookware));
    }

    [[nodiscard]]
    std::string response()
    const {
        using std::to_string, std::format;
        return name + "(￥" + to_string(price) + "/" + to_string(time) + "min, 收益率:" +
                format("{:.2f}", profit_rate) + ")";
    }
};


// 单个菜品的上架方案
struct MenuSolution {
    Dish dish;
    int count;
    double bar_ratio;  // 进度条拖动比例：三位小数

    explicit MenuSolution(
            Dish dish,
            const int count,
            const double bar_ratio
        ) :
        dish(std::move(dish)),
        count(count),
        bar_ratio(bar_ratio)
    {}

    [[nodiscard]]
    std::string response()
    const {
        using std::to_string, std::format;
        return "上架" + dish.name + " " + to_string(count) + "份，" +
                "进度条比例" + format("{:.3f}", bar_ratio) + "，" +
                "预计收益" + to_string(count * dish.price) + "，" +
                "预计耗时" + format("{:.1f}", count * dish.time / 60) + "h";
    }
};


// 决策结果
struct DecisionResult {
    std::vector<MenuSolution> solutions;
    std::unordered_map<std::string, int> purchase_plan; // 需要购买的食材种类及数量
    int total_profit;
    PurchaseStrategy strategy;

    explicit DecisionResult(
            std::vector<MenuSolution>& solutions,
            std::unordered_map<std::string, int>& purchase_plan,
            const int total_profit,
            const PurchaseStrategy strategy
        ) :
        solutions(std::move(solutions)),
        purchase_plan(std::move(purchase_plan)),
        total_profit(total_profit),
        strategy(strategy)
    {}

    [[nodiscard]]
    std::string response()
    const {
        using std::to_string, std::format, std::string;

        string string_strategy;
        switch (strategy) {
            case PurchaseStrategy::BUY_ALL:
                string_strategy = "buy_all";
                break;
            case PurchaseStrategy::NO_PURCHASE:
                string_strategy = "no_purchase";
                break;
            default:
                string_strategy = "buy_missing";
                break;
        }

        string lines = "策略: " + string_strategy + "，总预计收益:" + to_string(total_profit) + "\n";
        lines += "方案：";
        for (const auto& solution : solutions) {
            lines += solution.response() + "；";
        }

        if (!purchase_plan.empty()) {
            lines += "\n需购买食材:";
            for (const auto& [ingredient, count] : purchase_plan) {
                if (count > 0) {
                    lines += (ingredient + ": " + to_string(count) + "；");
                }
            }
        }

        return lines;
    }
};

