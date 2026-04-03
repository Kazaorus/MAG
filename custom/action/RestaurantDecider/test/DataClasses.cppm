export module DataClasses;

import "ContainerAlias.hpp";
import <string>;
import <unordered_map>;
import <stdexcept>;
import <format>;

import AssistFunctions;


export struct Dish {
    std::string name;
    std::string cookware;
    int price;
    double time;  //预计售卖时间（分钟）
    double profit_rate;
    int unlock_level;
    name_map ingredients{};  // 原始字符串映射（用于外部接口）
    sparse_indices ingredients_indexed{};  // 索引映射 {食材索引, 数量}（用于内部计算）

    explicit Dish(
            std::string name,
            const std::string_view cookware,
            const int price,
            const double time,
            const int unlock_level,
            name_map input_ingredients,
            const name_map& universal_indices  // 全局食材索引映射（初始化时建立）
        ) :
        name(std::move(name)),
        cookware(valid_cookware(cookware)),
        price(price),
        time(time),
        profit_rate(time > 0 ? static_cast<double>(price) / time : 0),
        unlock_level(unlock_level),
        ingredients(std::move(input_ingredients))
    {
        ingredients_indexed.reserve(ingredients.size());
        for (const auto& [ingredient, amount] : ingredients) {
            if (
                auto it = universal_indices.find(ingredient);
                it != universal_indices.end()
                ) {
                this->ingredients_indexed.emplace_back(it->second, amount);
            }
        }
    }

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


// 全局食材索引映射（单例）
export class DishIndices {
    name_map ingredients{};
    name_map ingredient_to_idx{};
    std::vector<std::string> idx_to_ingredient;

    std::vector<int> warehouse_amounts;  // 仓库基础量
    std::vector<int> shop_amounts;  // 商店增量

    DishIndices(
        const std::vector<std::string>& all_ingredient_names,
        const name_map& warehouse_storage,
        const name_map& shop_storage
        ) {
        // 定义食材索引
        int idx = 0;
        const int num_ingredients = static_cast<int>(all_ingredient_names.size());
        idx_to_ingredient.reserve(num_ingredients);
        for (const auto& name : all_ingredient_names) {
            ingredient_to_idx[name] = idx;
            idx_to_ingredient.push_back(name);
            ++idx;
        }

        // 填充初始值
        warehouse_amounts.resize(num_ingredients, 0);
        shop_amounts.resize(num_ingredients, 0);

        for (int i = 0; i < num_ingredients; ++i) {
            const auto& name = idx_to_ingredient[i];
            warehouse_amounts[i] = map_get(warehouse_storage, name, 0);
            shop_amounts[i] = map_get(shop_storage, name, 0);
        }
    }

public:
    static DishIndices GetInstance(
        const std::vector<std::string>& all_ingredient_names = {},
        const name_map& warehouse_storage = {},
        const name_map& shop_storage = {}
        ) {
        static DishIndices instance(all_ingredient_names, warehouse_storage, shop_storage);
        return instance;
    }
};