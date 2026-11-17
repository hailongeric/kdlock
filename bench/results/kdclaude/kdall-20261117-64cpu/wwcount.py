# Make a counting copy of test-ww_mutex.c: every stress failure counted per class,
# plus how often stress_inorder_work saw -EDEADLK and how many rounds it ran.
import sys
s = open(sys.argv[1]).read()
s = s.replace('#include <linux/ww_mutex.h>\n', '#include <linux/ww_mutex.h>\n\nstatic atomic_t kdc_fail, kdc_deadlk, kdc_rounds;\n', 1)
n = s.count('pr_err_once("stress (%s) failed with %d\\n",')
assert n == 3, n
s = s.replace('pr_err_once("stress (%s) failed with %d\\n",', 'atomic_inc(&kdc_fail); pr_err_ratelimited("stress (%s) failed with %d\\n",')
old = "\t\tif (err == -EDEADLK) {\n\t\t\tif (!time_after(jiffies, stress->timeout)) {\n\t\t\t\tww_mutex_lock_slow(&locks[order[contended]], &ctx);"
assert s.count(old) == 1
s = s.replace(old, "\t\tatomic_inc(&kdc_rounds);\n\t\tif (err == -EDEADLK)\n\t\t\tatomic_inc(&kdc_deadlk);\n" + old)
old = "\tret = stress(class, 16, 2 * ncpus, STRESS_INORDER);\n\tif (ret)\n\t\treturn ret;\n"
assert s.count(old) == 1
s = s.replace(old, "\tatomic_set(&kdc_fail, 0); atomic_set(&kdc_deadlk, 0); atomic_set(&kdc_rounds, 0);\n"
              "\tret = stress(class, 16, 2 * ncpus, STRESS_INORDER);\n"
              "\tpr_info(\"kdc %s inorder: rounds %d deadlk %d failed_workers %d\\n\", class->acquire_name,\n"
              "\t\tatomic_read(&kdc_rounds), atomic_read(&kdc_deadlk), atomic_read(&kdc_fail));\n"
              "\tif (ret)\n\t\treturn ret;\n")
open(sys.argv[2], "w").write(s)
