#include <stdio.h>

#define MAX_BUFFER 1024

struct Point {
    int x;
    int y;
};

int calculate_sum(int a, int b) {
    return a + b;
}

int main() {
    printf("Sum: %d\n", calculate_sum(10, 20));
    return 0;
}
