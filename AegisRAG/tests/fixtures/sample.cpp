#include <iostream>
#include <vector>

template <typename T>
class Container {
public:
    void add(const T& item) {
        items_.push_back(item);
    }
    size_t size() const {
        return items_.size();
    }
private:
    std::vector<T> items_;
};
