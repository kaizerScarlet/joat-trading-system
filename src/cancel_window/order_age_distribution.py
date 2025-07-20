"""
Order Age Distribution Module 

Tracks the age of active orders to understand whether orders are passive (long lived) or aggressive(shortlived)
- a feature tied to informed trading or liquidity stress

input:
*Order lifecylce (add, fill, cancel)

Logic:
*For each order, store timestamp_created 
*When the order is cancelled or filled, compute age.
*Use histogram or statiscal summary (e.g mean, std, quantiles)

Output:
*Age Distribution statistics
*Optional: Detection of unusual burst of short-leved orders
"""