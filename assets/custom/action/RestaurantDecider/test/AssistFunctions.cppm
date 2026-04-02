export module AssistFunctions;

import <string>;
import <unordered_map>;
import <generator>;
import <algorithm>;


// 从映射中获取值，若不存在则返回默认值
export template<typename T>
[[nodiscard]]
T map_get(const std::unordered_map<std::string, T>& map, const std::string& key, const T default_value) {
    if (auto it = map.find(key); it != map.end()) {
        return it->second;
    }
    return default_value;
}


// 返回所有组合
export template<typename T>
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
