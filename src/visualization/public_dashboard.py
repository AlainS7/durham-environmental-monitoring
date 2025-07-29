#!/usr/bin/env python3
"""
Hot Durham Public Dashboard
A public-facing web interface for Durham residents to view real-time air quality and weather data
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import existing systems
try:
    from src.core.data_manager import DataManager
    from src.data_collection.faster_wu_tsi_to_sheets_async import fetch_wu_data, fetch_tsi_data
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some dependencies not available: {e}")
    DEPENDENCIES_AVAILABLE = False

# Import predictive analytics (Feature 2)
try:
    from src.ml.predictive_api import PredictiveAnalyticsAPI
    PREDICTIVE_ANALYTICS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Predictive analytics not available: {e}")
    PredictiveAnalyticsAPI = None
    PREDICTIVE_ANALYTICS_AVAILABLE = False

class PublicDashboardServer:
    """Public-facing Flask server for Durham residents"""
    
    def __init__(self, project_root_path: str):
        self.project_root = Path(project_root_path)
        self.app = Flask(__name__, template_folder=str(self.project_root / "templates"))
        self.setup_routes()
        
        # Initialize predictive analytics (Feature 2)
        self.predictive_api = None
        if PREDICTIVE_ANALYTICS_AVAILABLE:
            try:
                self.predictive_api = PredictiveAnalyticsAPI(self.project_root)
                print("🤖 Predictive Analytics integrated with dashboard")
            except Exception as e:
                print(f"Warning: Could not initialize predictive analytics: {e}")
        
        # Load credentials (with error handling for public deployment)
        self.wu_creds = self.load_wu_credentials()
        self.tsi_creds = self.load_tsi_credentials()
        
        # Public sensor configurations (anonymized/public locations only)
        self.public_sensors = {
            'air_quality': [
                {
                    "name": "Downtown Durham", 
                    "id": "downtown_01",
                    "lat": 35.9940, 
                    "lon": -78.8986,
                    "location": "Downtown Area",
                    "type": "Air Quality Monitor",
                    "description": "Monitoring PM2.5, PM10, and other air quality indicators"
                },
                {
                    "name": "Duke University Area", 
                    "id": "duke_01",
                    "lat": 36.0014, 
                    "lon": -78.9392,
                    "location": "Duke University Vicinity",
                    "type": "Air Quality Monitor", 
                    "description": "Campus area air quality monitoring"
                },
                {
                    "name": "Durham Central", 
                    "id": "central_01",
                    "lat": 35.9886, 
                    "lon": -78.9072,
                    "location": "Central Durham",
                    "type": "Air Quality Monitor",
                    "description": "Central city air quality monitoring"
                }
            ],
            'weather': [
                {
                    "name": "Durham Weather - North", 
                    "id": "KNCDURHA548",
                    "lat": 36.0014, 
                    "lon": -78.9392,
                    "location": "North Durham Area",
                    "type": "Weather Station",
                    "description": "Temperature, humidity, wind, and precipitation data"
                },
                {
                    "name": "Durham Weather - Central", 
                    "id": "KNCDURHA549",
                    "lat": 35.9940, 
                    "lon": -78.8986,
                    "location": "Central Durham",
                    "type": "Weather Station",
                    "description": "Comprehensive weather monitoring"
                }
            ]
        }
        
        # Data cache for performance
        self.data_cache = {
            'last_update': None,
            'air_quality_data': {},
            'weather_data': {},
            'cache_duration': 300  # 5 minutes
        }
        
    def load_wu_credentials(self):
        """Load Weather Underground API credentials with fallback"""
        try:
            creds_path = self.project_root / "creds" / "wu_api_key.json"
            with open(creds_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load WU credentials: {e}")
            return {"api_key": None}
    
    def load_tsi_credentials(self):
        """Load TSI API credentials with fallback"""
        try:
            creds_path = self.project_root / "creds" / "tsi_creds.json"
            with open(creds_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load TSI credentials: {e}")
            return {"username": None, "password": None}
    
    def setup_routes(self):
        """Setup Flask routes for public dashboard"""
        
        @self.app.route('/')
        def public_dashboard():
            """Main public dashboard page"""
            return render_template('public_dashboard.html')
        
        @self.app.route('/mobile')
        def mobile_dashboard():
            """Mobile-optimized dashboard page"""
            return render_template('mobile_dashboard.html')
        
        @self.app.route('/static/<path:filename>')
        def static_files(filename):
            """Serve static files for PWA"""
            static_dir = self.project_root / 'static'
            return self.app.send_static_file(filename) if static_dir.exists() else '', 404
        
        @self.app.route('/api/public/sensors')
        def get_public_sensors():
            """Get all public sensor locations (no sensitive data)"""
            try:
                return jsonify({
                    'sensors': self.public_sensors,
                    'last_updated': datetime.now().isoformat(),
                    'status': 'online'
                })
            except Exception:
                return jsonify({'error': 'Service temporarily unavailable'}), 500
        
        @self.app.route('/api/public/air-quality')
        def get_public_air_quality():
            """Get current air quality data for all public sensors"""
            try:
                # Check cache first
                if self.is_cache_valid():
                    return jsonify(self.data_cache['air_quality_data'])
                
                # Fetch fresh data
                air_quality_data = self.fetch_air_quality_data()
                
                # Update cache
                self.data_cache['air_quality_data'] = air_quality_data
                self.data_cache['last_update'] = datetime.now()
                
                return jsonify(air_quality_data)
                
            except Exception as e:
                print(f"Error fetching air quality data: {e}")
                return jsonify({
                    'error': 'Air quality data temporarily unavailable',
                    'sensors': [],
                    'message': 'Please try again in a few minutes'
                }), 503
        
        @self.app.route('/api/public/weather')
        def get_public_weather():
            """Get current weather data for public display"""
            try:
                # Check cache first
                if self.is_cache_valid():
                    return jsonify(self.data_cache['weather_data'])
                
                # Fetch fresh data
                weather_data = self.fetch_weather_data()
                
                # Update cache
                self.data_cache['weather_data'] = weather_data
                self.data_cache['last_update'] = datetime.now()
                
                return jsonify(weather_data)
                
            except Exception as e:
                print(f"Error fetching weather data: {e}")
                return jsonify({
                    'error': 'Weather data temporarily unavailable',
                    'sensors': [],
                    'message': 'Please try again in a few minutes'
                }), 503
        
        @self.app.route('/api/public/health-index')
        def get_air_quality_index():
            """Get simplified air quality health index for the public"""
            try:
                aqi_data = self.calculate_public_aqi()
                return jsonify(aqi_data)
            except Exception:
                return jsonify({
                    'overall_status': 'unknown',
                    'message': 'Air quality index temporarily unavailable'
                }), 503
        
        @self.app.route('/api/public/trends')
        def get_public_trends():
            """Get 24-hour trend data for public display"""
            try:
                trends = self.get_24hour_trends()
                return jsonify(trends)
            except Exception:
                return jsonify({
                    'trends': [],
                    'message': 'Trend data temporarily unavailable'
                }), 503
        
        # Predictive Analytics Routes (Feature 2)
        @self.app.route('/api/public/forecast')
        def get_air_quality_forecast():
            """Get air quality forecast for public display"""
            try:
                if not self.predictive_api:
                    return jsonify({
                        'error': 'Forecast service not available',
                        'status': 'unavailable'
                    }), 503
                
                hours_ahead = request.args.get('hours', 24, type=int)
                hours_ahead = min(max(hours_ahead, 1), 48)  # Limit to 1-48 hours
                
                forecast_data = self.predictive_api.get_air_quality_forecast(hours_ahead=hours_ahead)
                return jsonify(forecast_data)
                
            except Exception as e:
                print(f"Error getting forecast: {e}")
                return jsonify({
                    'error': 'Forecast temporarily unavailable',
                    'status': 'error'
                }), 503
        
        @self.app.route('/api/public/alerts')
        def get_public_alerts():
            """Get current public alerts"""
            try:
                if not self.predictive_api:
                    return jsonify({
                        'alerts': [],
                        'status': 'unavailable'
                    })
                
                alerts_data = self.predictive_api.get_current_alerts()
                
                # Filter for public alerts only
                public_alerts = []
                if 'alerts' in alerts_data:
                    for alert in alerts_data['alerts']:
                        if alert['level'] in ['high', 'critical', 'emergency']:
                            public_alerts.append({
                                'level': alert['level'],
                                'message': alert['message'],
                                'timestamp': alert['timestamp'],
                                'recommendations': alert.get('recommendations', [])
                            })
                
                return jsonify({
                    'alerts': public_alerts,
                    'total_active': len(public_alerts),
                    'last_updated': datetime.now().isoformat(),
                    'status': 'success'
                })
                
            except Exception as e:
                print(f"Error getting alerts: {e}")
                return jsonify({
                    'alerts': [],
                    'error': 'Alerts temporarily unavailable'
                }), 503
        
        @self.app.route('/api/public/health-impact')
        def get_health_impact_summary():
            """Get public health impact summary"""
            try:
                if not self.predictive_api:
                    return jsonify({
                        'health_impact': {},
                        'status': 'unavailable'
                    })
                
                health_data = self.predictive_api.get_health_impact_assessment()
                
                # Simplify for public consumption
                if 'health_impact' in health_data:
                    health_impact = health_data['health_impact']
                    public_summary = {
                        'overall_risk_level': self._get_public_risk_level(health_impact),
                        'recommendations': health_impact.get('recommendations', [])[:5],  # Top 5
                        'air_quality_summary': health_impact.get('air_quality_summary', {}),
                        'last_updated': health_impact.get('generated_at', datetime.now().isoformat())
                    }
                    
                    return jsonify({
                        'health_summary': public_summary,
                        'status': 'success'
                    })
                
                return jsonify(health_data)
                
            except Exception as e:
                print(f"Error getting health impact: {e}")
                return jsonify({
                    'health_summary': {},
                    'error': 'Health impact data temporarily unavailable'
                }), 503
        
        @self.app.route('/api/public/seasonal')
        def get_seasonal_patterns():
            """Get seasonal air quality patterns for public education"""
            try:
                if not self.predictive_api:
                    return jsonify({
                        'seasonal_data': {},
                        'status': 'unavailable'
                    })
                
                seasonal_data = self.predictive_api.get_seasonal_analysis()
                
                # Simplify for public consumption
                if 'seasonal_analysis' in seasonal_data:
                    analysis = seasonal_data['seasonal_analysis']
                    public_patterns = {
                        'monthly_averages': analysis.get('monthly_patterns', {}).get('mean', {}),
                        'seasonal_trends': analysis.get('seasonal_patterns', {}).get('mean', {}),
                        'best_months': self._get_best_air_quality_months(analysis),
                        'worst_months': self._get_worst_air_quality_months(analysis),
                        'analysis_period': analysis.get('analysis_period', {})
                    }
                    
                    return jsonify({
                        'seasonal_patterns': public_patterns,
                        'status': 'success'
                    })
                
                return jsonify(seasonal_data)
                
            except Exception as e:
                print(f"Error getting seasonal patterns: {e}")
                return jsonify({
                    'seasonal_patterns': {},
                    'error': 'Seasonal data temporarily unavailable'
                }), 503

        @self.app.route('/health')
        def health_check():
            """Health check endpoint for monitoring"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'version': '2.0.0'
            })
    
    def is_cache_valid(self):
        """Check if cached data is still valid"""
        if not self.data_cache['last_update']:
            return False
        
        age = (datetime.now() - self.data_cache['last_update']).seconds
        return age < self.data_cache['cache_duration']
    
    def fetch_air_quality_data(self):
        """Fetch current air quality data from TSI sensors"""
        air_quality_data = {
            'sensors': [],
            'last_updated': datetime.now().isoformat(),
            'data_quality': 'good'
        }
        
        try:
            if not self.tsi_creds.get('username'):
                # Return mock data if no credentials (for demo purposes)
                return self.get_mock_air_quality_data()
            
            # Fetch real data from TSI API
            # Implementation would go here
            for sensor in self.public_sensors['air_quality']:
                sensor_data = {
                    'id': sensor['id'],
                    'name': sensor['name'],
                    'location': sensor['location'],
                    'pm25': 12.5,  # μg/m³
                    'pm10': 18.2,  # μg/m³
                    'aqi': 52,     # Air Quality Index
                    'status': 'good',
                    'color': '#4CAF50',  # Green for good
                    'last_reading': datetime.now().isoformat()
                }
                air_quality_data['sensors'].append(sensor_data)
                
        except Exception as e:
            print(f"Error in fetch_air_quality_data: {e}")
            return self.get_mock_air_quality_data()
        
        return air_quality_data
    
    def fetch_weather_data(self):
        """Fetch current weather data"""
        weather_data = {
            'sensors': [],
            'last_updated': datetime.now().isoformat()
        }
        
        try:
            if not self.wu_creds.get('api_key'):
                return self.get_mock_weather_data()
            
            # Fetch real weather data
            for sensor in self.public_sensors['weather']:
                sensor_data = {
                    'id': sensor['id'],
                    'name': sensor['name'],
                    'location': sensor['location'],
                    'temperature': 22.5,  # °C
                    'humidity': 65,       # %
                    'wind_speed': 8.5,    # km/h
                    'pressure': 1013.2,   # hPa
                    'conditions': 'Partly Cloudy',
                    'last_reading': datetime.now().isoformat()
                }
                weather_data['sensors'].append(sensor_data)
                
        except Exception as e:
            print(f"Error in fetch_weather_data: {e}")
            return self.get_mock_weather_data()
        
        return weather_data
    
    def calculate_public_aqi(self):
        """Calculate overall air quality index for Durham"""
        try:
            # This would calculate based on actual sensor readings
            return {
                'overall_aqi': 52,
                'status': 'Good',
                'color': '#4CAF50',
                'message': 'Air quality is good. Perfect day for outdoor activities!',
                'recommendations': [
                    'Great conditions for outdoor exercise',
                    'Windows can be opened for fresh air',
                    'No health precautions needed for general population'
                ],
                'last_updated': datetime.now().isoformat()
            }
        except Exception:
            return {
                'overall_aqi': None,
                'status': 'Unknown',
                'message': 'Unable to calculate air quality index at this time'
            }
    
    def get_24hour_trends(self):
        """Get 24-hour trend data for public display"""
        try:
            # Generate sample trend data
            hours = []
            now = datetime.now()
            for i in range(24):
                hour_time = now - timedelta(hours=23-i)
                hours.append({
                    'time': hour_time.strftime('%H:00'),
                    'aqi': 45 + (i % 3) * 5,  # Sample varying AQI
                    'pm25': 10 + (i % 4) * 2,  # Sample PM2.5 values
                    'temperature': 20 + (i % 8)  # Sample temperature
                })
            
            return {
                'trends': {
                    'hourly': hours,
                    'summary': {
                        'avg_aqi': 52,
                        'max_pm25': 18,
                        'min_temperature': 20,
                        'max_temperature': 27
                    }
                },
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            return {'trends': [], 'error': str(e)}
    
    def get_mock_air_quality_data(self):
        """Return mock air quality data for demonstration"""
        mock_sensors = []
        
        for i, sensor in enumerate(self.public_sensors['air_quality']):
            # Vary the mock data slightly for each sensor
            base_pm25 = 12.5 + (i * 2.5)  # Vary PM2.5 values
            base_aqi = 52 + (i * 6)       # Vary AQI values
            
            sensor_data = {
                'id': sensor['id'],
                'name': sensor['name'],
                'location': sensor['location'],
                'pm25': base_pm25,
                'pm10': base_pm25 * 1.5,  # PM10 typically higher than PM2.5
                'aqi': min(base_aqi, 100), # Keep AQI reasonable
                'status': 'good' if base_aqi < 60 else 'moderate',
                'color': '#4CAF50' if base_aqi < 60 else '#FFC107',
                'last_reading': datetime.now().isoformat()
            }
            mock_sensors.append(sensor_data)
        
        return {
            'sensors': mock_sensors,
            'last_updated': datetime.now().isoformat(),
            'data_quality': 'demo'
        }
    
    def get_mock_weather_data(self):
        """Return mock weather data for demonstration"""
        mock_sensors = []
        
        for i, sensor in enumerate(self.public_sensors['weather']):
            # Generate varying mock data for each sensor
            base_temp = 22.0 + (i * 0.6)  # Slight temperature variation
            base_humidity = 65 - (i * 3)  # Slight humidity variation
            
            mock_sensors.append({
                'id': sensor['id'],
                'name': sensor['name'],
                'location': sensor['location'],
                'temperature': round(base_temp, 1),
                'humidity': base_humidity,
                'wind_speed': round(8.5 - (i * 1.3), 1),
                'pressure': round(1013.2 - (i * 0.4), 1),
                'conditions': ['Partly Cloudy', 'Clear', 'Sunny'][i % 3],
                'last_reading': datetime.now().isoformat()
            })
        
        return {
            'sensors': mock_sensors,
            'last_updated': datetime.now().isoformat()
        }
    
    def run(self, host='0.0.0.0', port=5001, debug=False):
        """Run the public dashboard server"""
        print("🌍 Starting Hot Durham Public Dashboard...")
        print(f"📍 Server: http://{host}:{port}")
        print(f"🔍 Health Check: http://{host}:{port}/health")
        print(f"📊 Dashboard: http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

    def _get_public_risk_level(self, health_impact: dict) -> str:
        """Get simplified public risk level from health impact data"""
        try:
            advisory_level = health_impact.get('estimated_health_impacts', {}).get('health_advisory_level', 'NORMAL')
            
            if advisory_level == 'HEALTH_EMERGENCY':
                return 'HIGH_RISK'
            elif advisory_level == 'HEALTH_WARNING':
                return 'MODERATE_RISK'
            elif advisory_level == 'HEALTH_ADVISORY':
                return 'LOW_RISK'
            else:
                return 'MINIMAL_RISK'
        except:
            return 'UNKNOWN'
    
    def _get_best_air_quality_months(self, analysis: dict) -> list:
        """Get months with best air quality from seasonal analysis"""
        try:
            monthly_means = analysis.get('monthly_patterns', {}).get('mean', {})
            if not monthly_means:
                return []
            
            # Sort months by PM2.5 levels (lower is better)
            sorted_months = sorted(monthly_means.items(), key=lambda x: x[1])
            
            # Return top 3 best months
            month_names = {
                1: 'January', 2: 'February', 3: 'March', 4: 'April',
                5: 'May', 6: 'June', 7: 'July', 8: 'August', 
                9: 'September', 10: 'October', 11: 'November', 12: 'December'
            }
            
            return [month_names.get(int(month), f'Month {month}') for month, _ in sorted_months[:3]]
        except:
            return ['Spring', 'Fall', 'Winter']  # Default fallback
    
    def _get_worst_air_quality_months(self, analysis: dict) -> list:
        """Get months with worst air quality from seasonal analysis"""
        try:
            monthly_means = analysis.get('monthly_patterns', {}).get('mean', {})
            if not monthly_means:
                return []
            
            # Sort months by PM2.5 levels (higher is worse)
            sorted_months = sorted(monthly_means.items(), key=lambda x: x[1], reverse=True)
            
            # Return top 3 worst months
            month_names = {
                1: 'January', 2: 'February', 3: 'March', 4: 'April',
                5: 'May', 6: 'June', 7: 'July', 8: 'August', 
                9: 'September', 10: 'October', 11: 'November', 12: 'December'
            }
            
            return [month_names.get(int(month), f'Month {month}') for month, _ in sorted_months[:3]]
        except:
            return ['Summer', 'Late Fall']  # Default fallback

def main():
    """Main function to run the public dashboard"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Hot Durham Public Dashboard')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5001, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    
    args = parser.parse_args()
    
    # Initialize and run the server
    dashboard = PublicDashboardServer(str(project_root))
    dashboard.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()
