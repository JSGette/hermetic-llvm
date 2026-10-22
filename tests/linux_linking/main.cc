#include <iostream>
#include <stdexcept>
#include <thread>

struct Tracker {
    ~Tracker() { std::cout << "thread_local destroyed\n"; }
};

thread_local Tracker tracker;

int main() {
    std::thread([] { (void)tracker; }).join();
    try {
        throw std::runtime_error("hello from linux linking test");
    } catch (const std::exception& e) {
        std::cout << e.what() << "\n";
    }
    return 0;
}
