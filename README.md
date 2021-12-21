# ZephyrIncludeMap
Header include map generator for Zephyr RTOS

This tool generate include map for a Zephyr C source file.
The generation is based on C preprocessor result.
So it is not necessarily exactly the same as what you see in C source file.
For example, a xxx.h file with include guard will not be included at a certain position
if a previous yyy.h file has included it indirectly.
So the include map will only show the xxx.h file under yyy.h.

In short, it reflects the final effecive result of the include hierarchy.

