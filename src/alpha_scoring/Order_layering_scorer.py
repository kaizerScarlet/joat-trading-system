from typing import List, Dict 
from cancel_window.order_layering_detection import OrderLayeringDetection

class LayeringScoring:
    def __init__(self, reference_size: float = 5.0, base_score: float= 1.0):
        """
        :param reference_size: Normalizing size for order weighting
        :param base_score: Base multiplier per cluster
        """

        self.reference_size = reference_size
        self.base_score = base_score
        self.layering_detector = OrderLayeringDetection()
        self.last_score =  0.0


    def register_order(self, timestamp: int, price: float, size: float, side: str):
        self.layering_detector.register_order(timestamp, price, size, side)

    def compute_score(self, current_time: int) -> float:
        clusters = self.layering_detector.detect_layering()

        total_score = 0.0
        for cluster in clusters:
            
            cluster_size = sum(order['size'] for orders in cluster['cluster'])
            normalized_size = cluster_size / self.reference_size
            cluster_score = self.base_score * normalized_size

            total_score += cluster_score
        self.last_score = total_score
        return total_score
    
    def reset(self):
        self.layering_detector.reset()
        self.last_score = 0.0
