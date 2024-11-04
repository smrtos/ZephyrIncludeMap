# ZephyrIncludeMap
Header include map generator for Zephyr RTOS

This tool generates include map for a Zephyr C source file.
The generation is based on C preprocessor result.
So it is NOT necessarily exactly the same as what you see in C source file.

For example, a xxx.h file with include guard will not be included at a certain position
if a previous yyy.h file has included it indirectly first.
The include map will only show the xxx.h file under yyy.h.

In short, it reflects the final effecive result of the include hierarchy.
But it is good enough, isn't it?

A sample command:

> python3 GenIncludeMap2.py  ~/sources/zephyrproject/zephyr/ ~/sources/zephyrproject/zephyr/build ~/dev/toolchain/arm32-none-eabi/bin/arm-none-eabi-gcc ~/dev/toolchain/arm32-none-eabi/lib/gcc/arm-none-eabi/13.3.1/include ~/sources/zephyrproject/zephyr/samples/drivers/uart/echo_bot/src/main.c

