# Zephyr Include Map
This tool generates include map for a Zephyr RTOS C source file.
The generation is based on C preprocessor result.
So it is NOT necessarily exactly the same as what you see in C source file.

For example, A xxx.h file with include guard will not be included at a certain position
of yyy.c if a previous zzz.h in yyy.c has included xxx.h already.
The include map will only show the xxx.h file under zzz.h rather than under yyy.c.

In short, it reflects the final effective result of the include hierarchy.
But it is good enough, isn't it?

And for a single C file, the header included earlier appears more left in the graph.

```
IncludeMap ver 0.22
By Shao Ming (smwikipedia@163.com, smrtos@163.com)
[Description]:
  This tool generates a map of included headers for a Zephyr .c file in the context of a Zephyr build.
[Pre-condition]:
  A Zephyr build must be made before using this tool because some build-generated files are needed.
[Usage]:
  GenIncludeMap <srcDir> <bldDir> <gccFullPath> <srcFileFullPath>
  <zephyrDir>: the Zephyr folder path.
  <bldDir>: the Zephyr build folder where build.ninja file is located.
  <gccFullPath>: the full path of the GCC used to build Zephyr.
  <srcFileFullPath>: the full path of the Zephyr source file to generate include map for.
```

A sample command:

> python3 GenIncludeMap2.py  ~/sources/zephyrproject/zephyr/ ~/sources/zephyrproject/zephyr/build ~/dev/toolchain/arm32-none-eabi/bin/arm-none-eabi-gcc ~/sources/zephyrproject/zephyr/samples/drivers/uart/echo_bot/src/main.c

