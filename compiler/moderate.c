int calculate(int a, int b)
{
    int result;

    if (a > b)
    {
        result = a - b;
    }
    else
    {
        result = b - a;
    }

    return result;
}

int main()
{
    int a;
    int b;
    int result;
    int i;

    a = 20;
    b = 10;

    result = calculate(a, b);

    for (i = 0; i < 5; i++)
    {
        result = result + i;
    }

    if (result > 30)
    {
        result = result - 5;
    }
    else
    {
        result = result + 5;
    }

    return 0;
}