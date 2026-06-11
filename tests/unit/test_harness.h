/*
 * test_harness.h — minimal unit test macros.
 * Usage:
 *   TEST(name) { ... ASSERT_EQ(a, b); ... }
 *   int main() { RUN_TEST(name); REPORT(); }
 */
#ifndef TEST_HARNESS_H
#define TEST_HARNESS_H

#include <stdio.h>

static int _tests_run = 0;
static int _tests_passed = 0;
static int _tests_failed = 0;
static const char *_current_test = "";

#define TEST(name) static void test_##name(void)

#define RUN_TEST(name) do {                                   \
    _current_test = #name;                                    \
    _tests_run++;                                             \
    test_##name();                                            \
    if (_tests_run == _tests_passed + _tests_failed)          \
        /* test didn't assert anything? count as pass */      \
        _tests_passed++;                                      \
    printf("  [PASS] %s\n", #name);                           \
} while (0)

#define ASSERT(cond) do {                                     \
    if (!(cond)) {                                            \
        printf("  [FAIL] %s: %s (line %d)\n",                 \
               _current_test, #cond, __LINE__);               \
        _tests_failed++;                                      \
        _tests_passed--; /* offset the auto-pass */           \
        return;                                               \
    }                                                         \
} while (0)

#define ASSERT_EQ(a, b) do {                                  \
    typeof(a) _a = (a); typeof(b) _b = (b);                  \
    if (_a != _b) {                                           \
        printf("  [FAIL] %s: %s == %s → %ld != %ld (line %d)\n", \
               _current_test, #a, #b,                         \
               (long)_a, (long)_b, __LINE__);                 \
        _tests_failed++;                                      \
        _tests_passed--;                                      \
        return;                                               \
    }                                                         \
} while (0)

#define ASSERT_NE(a, b) do {                                  \
    typeof(a) _a = (a); typeof(b) _b = (b);                  \
    if (_a == _b) {                                           \
        printf("  [FAIL] %s: %s != %s → both %ld (line %d)\n", \
               _current_test, #a, #b, (long)_a, __LINE__);   \
        _tests_failed++;                                      \
        _tests_passed--;                                      \
        return;                                               \
    }                                                         \
} while (0)

#define REPORT() do {                                         \
    printf("\n%d tests: %d passed, %d failed\n",              \
           _tests_run, _tests_passed, _tests_failed);         \
    return _tests_failed > 0 ? 1 : 0;                        \
} while (0)

#endif /* TEST_HARNESS_H */
