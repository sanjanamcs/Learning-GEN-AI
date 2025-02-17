import os, sys   # Unused imports

def add_numbers(a, b):
   """Adds two numbers and returns the result."""
   return a+b  # Formatting issue (spacing around operator)

def divide_numbers(a, b):
    """Divides two numbers, handling division by zero."""
    try:
        return a / b
    except ZeroDivisionError:
        print("Cannot divide by zero")  # No logging used

print(add_numbers(5,10))
print(divide_numbers(10, 0))
