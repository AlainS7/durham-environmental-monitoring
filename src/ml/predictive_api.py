#!/usr/bin/env python3
"""
Predictive Analytics API Integration
Feature 2 Implementation - Integration with existing dashboard and web systems

This module provides:
- API endpoints for predictive analytics
- Integration with existing public dashboard
- Real-time predictions and alerts
- Mobile-friendly JSON responses
"""

from flask import Flask, jsonify, request # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Dict, List

# Add project paths
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root / "src" / "ml"))
sys.path.append(str(project_root / "src" / "visualization"))

try:
    from predictive_analytics import PredictiveAnalytics
    from enhanced_anomaly_detection import EnhancedAnomalyDetector
except ImportError as e:
    print(f"Warning: Could not import ML modules: {e}")
    PredictiveAnalytics = None
    EnhancedAnomalyDetector = None

class PredictiveAnalyticsAPI:
    """API wrapper for predictive analytics functionality."""
    
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else project_root
        
        # Initialize ML systems
        self.analytics = None
        self.anomaly_detector = None
        
        try:
            if PredictiveAnalytics:
                self.analytics = PredictiveAnalytics(self.base_dir)
            if EnhancedAnomalyDetector:
                self.anomaly_detector = EnhancedAnomalyDetector(self.base_dir)
        except Exception as e:
            print(f"Warning: Could not initialize ML systems: {e}")
        
        # Cache for predictions
        self.prediction_cache = {}
        self.cache_expiry = timedelta(hours=1)
        
        print("🤖 Predictive Analytics API initialized")

    def get_air_quality_forecast(self, hours_ahead: int = 24) -> Dict:
        """Get air quality forecast with caching."""
        cache_key = f"forecast_{hours_ahead}h"
        now = datetime.now()
        
        # Check cache
        if (cache_key in self.prediction_cache and 
            now - self.prediction_cache[cache_key]['timestamp'] < self.cache_expiry):
            return self.prediction_cache[cache_key]['data']
        
        try:
            if not self.analytics:
                return {
                    'error': 'Predictive analytics system not available',
                    'status': 'unavailable'
                }
            
            # Generate predictions
            predictions = self.analytics.predict_air_quality(hours_ahead=hours_ahead)
            
            if 'error' in predictions:
                return predictions
            
            # Format for API response
            formatted_predictions = {
                'forecast': {
                    'generated_at': predictions['generated_at'],
                    'hours_ahead': hours_ahead,
                    'predictions': predictions['predictions'],
                    'model_info': {
                        'model_used': predictions.get('model_used', 'unknown'),
                        'confidence_level': 'medium'
                    }
                },
                'current_conditions': self._get_current_conditions(),
                'health_advisory': self._get_health_advisory(predictions['predictions']),
                'status': 'success'
            }
            
            # Cache results
            self.prediction_cache[cache_key] = {
                'timestamp': now,
                'data': formatted_predictions
            }
            
            return formatted_predictions
            
        except Exception as e:
            return {
                'error': f'Forecast generation failed: {str(e)}',
                'status': 'error',
                'timestamp': now.isoformat()
            }

    def get_current_alerts(self) -> Dict:
        """Get current active alerts."""
        try:
            if not self.anomaly_detector:
                return {
                    'alerts': [],
                    'status': 'unavailable',
                    'message': 'Alert system not available'
                }
            
            active_alerts = self.anomaly_detector.get_active_alerts()
            alert_summary = self.anomaly_detector.generate_alert_summary()
            
            # Format alerts for API
            formatted_alerts = []
            for alert_id, alert in active_alerts.items():
                formatted_alerts.append({
                    'id': alert_id,
                    'type': alert['type'],
                    'level': alert['level'],
                    'message': alert['message'],
                    'timestamp': alert['timestamp'],
                    'recommendations': alert.get('recommendations', []),
                    'status': alert.get('status', 'active')
                })
            
            return {
                'alerts': formatted_alerts,
                'summary': alert_summary,
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'alerts': [],
                'error': f'Alert retrieval failed: {str(e)}',
                'status': 'error',
                'timestamp': datetime.now().isoformat()
            }

    def get_seasonal_analysis(self) -> Dict:
        """Get seasonal pattern analysis."""
        try:
            if not self.analytics:
                return {
                    'error': 'Seasonal analysis not available',
                    'status': 'unavailable'
                }
            
            # Check if we need to load data
            if self.analytics.historical_data.empty:
                if not self.analytics.load_historical_data():
                    return {
                        'error': 'No historical data available for seasonal analysis',
                        'status': 'no_data'
                    }
            
            seasonal_data = self.analytics.analyze_seasonal_patterns()
            
            if 'error' in seasonal_data:
                return seasonal_data
            
            return {
                'seasonal_analysis': seasonal_data,
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': f'Seasonal analysis failed: {str(e)}',
                'status': 'error',
                'timestamp': datetime.now().isoformat()
            }

    def get_health_impact_assessment(self) -> Dict:
        """Get health impact assessment."""
        try:
            if not self.analytics:
                return {
                    'error': 'Health impact analysis not available',
                    'status': 'unavailable'
                }
            
            # Check if we need to load data
            if self.analytics.historical_data.empty:
                if not self.analytics.load_historical_data():
                    return {
                        'error': 'No historical data available for health impact analysis',
                        'status': 'no_data'
                    }
            
            health_report = self.analytics.generate_health_impact_report()
            
            if 'error' in health_report:
                return health_report
            
            return {
                'health_impact': health_report,
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': f'Health impact assessment failed: {str(e)}',
                'status': 'error',
                'timestamp': datetime.now().isoformat()
            }

    def _get_current_conditions(self) -> Dict:
        """Get current environmental conditions."""
        try:
            if self.analytics and not self.analytics.historical_data.empty:
                latest = self.analytics.historical_data.tail(1).iloc[0]
                return {
                    'pm25': latest.get('pm25', None),
                    'temperature': latest.get('temperature', None),
                    'humidity': latest.get('humidity', None),
                    'timestamp': latest.get('timestamp', datetime.now()).isoformat() if 'timestamp' in latest else datetime.now().isoformat()
                }
        except Exception:
            pass
        
        return {
            'pm25': None,
            'temperature': None,
            'humidity': None,
            'timestamp': datetime.now().isoformat(),
            'status': 'unavailable'
        }

    def _get_health_advisory(self, predictions: List[Dict]) -> Dict:
        """Generate health advisory based on predictions."""
        if not predictions:
            return {'level': 'unknown', 'message': 'No predictions available'}
        
        # Get next 24 hours of predictions
        next_24h = [p for p in predictions if p['hours_ahead'] <= 24]
        if not next_24h:
            return {'level': 'unknown', 'message': 'No short-term predictions available'}
        
        # Find highest predicted PM2.5 level
        max_pm25 = max(p['predicted_pm25'] for p in next_24h)
        avg_pm25 = sum(p['predicted_pm25'] for p in next_24h) / len(next_24h)
        
        # Determine advisory level
        if max_pm25 >= 150:
            level = 'emergency'
            message = f"Health Emergency: Extremely high air pollution expected (max {max_pm25:.1f} μg/m³)"
        elif max_pm25 >= 55:
            level = 'warning'
            message = f"Health Warning: Unhealthy air quality expected (max {max_pm25:.1f} μg/m³)"
        elif max_pm25 >= 35:
            level = 'advisory'
            message = f"Health Advisory: Elevated air pollution for sensitive groups (max {max_pm25:.1f} μg/m³)"
        elif avg_pm25 > 15:
            level = 'watch'
            message = f"Air Quality Watch: Monitor conditions (avg {avg_pm25:.1f} μg/m³)"
        else:
            level = 'good'
            message = f"Good Air Quality: Conditions expected to remain healthy (avg {avg_pm25:.1f} μg/m³)"
        
        return {
            'level': level,
            'message': message,
            'max_pm25_24h': round(max_pm25, 1),
            'avg_pm25_24h': round(avg_pm25, 1)
        }

    def process_real_time_data(self, sensor_data: Dict) -> Dict:
        """Process real-time sensor data and generate alerts if needed."""
        try:
            results = {
                'processed_at': datetime.now().isoformat(),
                'input_data': sensor_data,
                'alerts': [],
                'status': 'success'
            }
            
            # Generate alerts if anomaly detector is available
            if self.anomaly_detector:
                alerts = self.anomaly_detector.detect_real_time_anomalies(sensor_data)
                results['alerts'] = alerts
            
            return results
            
        except Exception as e:
            return {
                'error': f'Real-time processing failed: {str(e)}',
                'status': 'error',
                'timestamp': datetime.now().isoformat()
            }

# Flask app setup
def create_predictive_api_app():
    """Create Flask app with predictive analytics endpoints."""
    app = Flask(__name__)
    api = PredictiveAnalyticsAPI()
    
    @app.route('/api/v1/predict/air-quality')
    def get_air_quality_forecast():
        """Get air quality forecast."""
        hours_ahead = request.args.get('hours', 24, type=int)
        hours_ahead = min(max(hours_ahead, 1), 48)  # Limit to 1-48 hours
        
        result = api.get_air_quality_forecast(hours_ahead=hours_ahead)
        return jsonify(result)
    
    @app.route('/api/v1/alerts/current')
    def get_current_alerts():
        """Get current active alerts."""
        result = api.get_current_alerts()
        return jsonify(result)
    
    @app.route('/api/v1/analysis/seasonal')
    def get_seasonal_analysis():
        """Get seasonal pattern analysis."""
        result = api.get_seasonal_analysis()
        return jsonify(result)
    
    @app.route('/api/v1/health/impact')
    def get_health_impact():
        """Get health impact assessment."""
        result = api.get_health_impact_assessment()
        return jsonify(result)
    
    @app.route('/api/v1/realtime/process', methods=['POST'])
    def process_realtime_data():
        """Process real-time sensor data."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided', 'status': 'error'}), 400
            
            result = api.process_real_time_data(data)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                'error': f'Request processing failed: {str(e)}',
                'status': 'error'
            }), 500
    
    @app.route('/api/v1/status')
    def get_system_status():
        """Get system status."""
        return jsonify({
            'predictive_analytics': 'available' if api.analytics else 'unavailable',
            'anomaly_detection': 'available' if api.anomaly_detector else 'unavailable',
            'cache_entries': len(api.prediction_cache),
            'timestamp': datetime.now().isoformat(),
            'status': 'online'
        })
    
    @app.route('/api/v1/docs')
    def api_documentation():
        """API documentation."""
        docs = {
            'title': 'Hot Durham Predictive Analytics API',
            'version': '1.0',
            'endpoints': {
                '/api/v1/predict/air-quality': {
                    'method': 'GET',
                    'description': 'Get air quality forecast',
                    'parameters': {
                        'hours': 'Number of hours ahead to predict (1-48, default: 24)'
                    }
                },
                '/api/v1/alerts/current': {
                    'method': 'GET',
                    'description': 'Get current active alerts'
                },
                '/api/v1/analysis/seasonal': {
                    'method': 'GET',
                    'description': 'Get seasonal pattern analysis'
                },
                '/api/v1/health/impact': {
                    'method': 'GET',
                    'description': 'Get health impact assessment'
                },
                '/api/v1/realtime/process': {
                    'method': 'POST',
                    'description': 'Process real-time sensor data',
                    'body': {
                        'pm25': 'PM2.5 reading',
                        'temperature': 'Temperature reading',
                        'humidity': 'Humidity reading'
                    }
                },
                '/api/v1/status': {
                    'method': 'GET',
                    'description': 'Get system status'
                }
            }
        }
        return jsonify(docs)
    
    return app

def main():
    """Main function for standalone testing."""
    print("🤖 Hot Durham Predictive Analytics API")
    print("=" * 50)
    
    # Initialize API
    api = PredictiveAnalyticsAPI()
    
    # Test endpoints
    print("\n🧪 Testing API endpoints...")
    
    # Test forecast
    print("📈 Testing air quality forecast...")
    forecast = api.get_air_quality_forecast(hours_ahead=24)
    if forecast['status'] == 'success':
        predictions = forecast['forecast']['predictions']
        print(f"  ✅ Generated {len(predictions)} predictions")
        if predictions:
            next_hour = predictions[0]
            print(f"  🔮 Next hour: {next_hour['predicted_pm25']:.1f} μg/m³ ({next_hour['health_category']})")
    else:
        print(f"  ❌ Forecast failed: {forecast.get('error', 'Unknown error')}")
    
    # Test alerts
    print("\n🚨 Testing alerts...")
    alerts = api.get_current_alerts()
    if alerts['status'] == 'success':
        print(f"  ✅ Retrieved {len(alerts['alerts'])} active alerts")
    else:
        print(f"  ❌ Alerts failed: {alerts.get('error', 'Unknown error')}")
    
    # Test real-time processing
    print("\n⚡ Testing real-time processing...")
    test_data = {
        'pm25': 45.2,
        'temperature': 74.5,
        'humidity': 68.3
    }
    
    result = api.process_real_time_data(test_data)
    if result['status'] == 'success':
        print(f"  ✅ Processed data successfully, generated {len(result['alerts'])} alerts")
    else:
        print(f"  ❌ Processing failed: {result.get('error', 'Unknown error')}")
    
    print("\n🌐 API ready for integration with dashboard")
    print("   Endpoints available at /api/v1/")

if __name__ == "__main__":
    # For development, can run Flask app
    if len(sys.argv) > 1 and sys.argv[1] == 'serve':
        import argparse
        parser = argparse.ArgumentParser(description='Hot Durham Predictive API Server')
        parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
        parser.add_argument('--port', type=int, default=5004, help='Port to bind to (default: 5004)')
        parser.add_argument('--debug', action='store_true', help='Run in debug mode')
        parser.add_argument('serve', help='Start the API server')
        
        args = parser.parse_args()
        
        app = create_predictive_api_app()
        print(f"🌐 Starting Hot Durham Predictive API Server on http://{args.host}:{args.port}")
        app.run(debug=args.debug, host=args.host, port=args.port)
    else:
        main()
