int calculate(int n, int limit) {
    int sum = 0;
    int i = 0;

    while (i < n) {
        if (i % 2 == 0) {

            if (i < limit) {
                sum = sum + i;
            } else {
                if (sum > 100) {
                    sum = sum - 10;
                } else {
                    sum = sum + 5;
                }
            }

        } else {

            if (i > 10) {
                sum = sum + i * 2;
            } else {
                sum = sum + i;
            }
        }

        i++;
    }

    return sum;
}


int process(int value) {
    int result = 0;

    if (value > 100) {

        if (value > 500) {
            result = value - 100;
        } else {
            if (value > 250) {
                result = value - 50;
            } else {
                result = value + 25;
            }
        }

    } else {

        if (value > 50) {
            result = value * 2;
        } else {
            result = value + 10;
        }
    }

    return result;
}


int main() {
    int n = 20;
    int limit = 10;
    int result = 0;

    result = calculate(n, limit);

    if (result > 200) {
        result = process(result);

        if (result > 500) {
            result = result - 100;
        }
    } else {
        result = process(result);

        if (result < 50) {
            result = result + 50;
        } else {
            result = result - 10;
        }
    }

    return result;
}