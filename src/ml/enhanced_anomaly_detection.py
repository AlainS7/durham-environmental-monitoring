#!/usr/bin/env python3
"""
Enhanced Anomaly Detection with Automated Alerting
Feature 2 Implementation - Smart Alerting System Integration

This module enhances the existing anomaly detection system with:
- Real-time anomaly detection
- Automated alert generation
- Multi-channel notifications (email, webhook, file-based)
- Configurable thresholds and sensitivity
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json
import warnings
from typing import Dict, List
import smtplib
import requests
import logging

sys.path.append(str(Path(__file__).parent.parent / "analysis"))
from ..analysis.anomaly_detection_and_trend_analysis import AnomalyDetectionSystem  # type: ignore

# Email imports (fix namespace issue)
try:
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    print("Warning: Email functionality not available")
    EMAIL_AVAILABLE = False

warnings.filterwarnings('ignore')

class EnhancedAnomalyDetector(AnomalyDetectionSystem):
    """Enhanced anomaly detection system with automated alerting capabilities."""
    
    def __init__(self, base_dir=None):
        super().__init__(base_dir)
        
        # Enhanced configuration
        self.alerts_dir = self.base_dir / "reports" / "alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        
        # Alert configuration
        self.alert_config = self.load_alert_configuration()
        self.active_alerts = {}
        self.alert_history = []
        
        # Setup logging
        self.setup_logging()
        
        print("🚨 Enhanced Anomaly Detection System initialized")
        print(f"📧 Alerts directory: {self.alerts_dir}")

    def load_alert_configuration(self) -> Dict:
        """Load or create alert system configuration."""
        config_candidates = [
            self.base_dir / "src" / "config" / "alert_system_config.json",
            self.base_dir / "config" / "alert_system_config.json",
        ]
        config_file = next((path for path in config_candidates if path.exists()), config_candidates[0])
        
        default_config = {
            "alert_thresholds": {
                "pm25": {
                    "critical": 150.0,
                    "high": 55.5,
                    "moderate": 35.5,
                    "consecutive_readings": 3
                },
                "temperature": {
                    "extreme_high": 40.0,
                    "extreme_low": -20.0,
                    "consecutive_readings": 2
                },
                "humidity": {
                    "extreme_high": 95.0,
                    "extreme_low": 5.0,
                    "consecutive_readings": 3
                },
                "data_quality": {
                    "missing_data_hours": 6,
                    "stuck_values_percentage": 20.0,
                    "outlier_count_threshold": 10
                }
            },
            "notification_channels": {
                "email": {
                    "enabled": False,
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "sender_email": "",
                    "recipients": []
                },
                "webhook": {
                    "enabled": False,
                    "url": "",
                    "headers": {"Content-Type": "application/json"}
                },
                "file_alerts": {
                    "enabled": True,
                    "alert_file": "current_alerts.json",
                    "history_file": "alert_history.json"
                }
            },
            "alert_rules": {
                "cooldown_minutes": 60,
                "escalation_hours": 24,
                "auto_resolve_hours": 2,
                "priority_levels": ["low", "medium", "high", "critical", "emergency"]
            }
        }
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults for any missing keys
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            except Exception as e:
                print(f"⚠️ Error loading alert config, using defaults: {e}")
        
        # Save default config
        config_file.parent.mkdir(exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_config

    def setup_logging(self):
        """Setup logging for alert system."""
        log_file = self.alerts_dir / "alert_system.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def detect_real_time_anomalies(self, current_data: Dict) -> List[Dict]:
        """Detect anomalies in real-time data and generate alerts."""
        alerts = []
        timestamp = datetime.now()
        
        # Air quality alerts
        if 'pm25' in current_data:
            pm25_alerts = self._check_pm25_alerts(current_data['pm25'], timestamp)
            alerts.extend(pm25_alerts)
        
        # Temperature alerts
        if 'temperature' in current_data:
            temp_alerts = self._check_temperature_alerts(current_data['temperature'], timestamp)
            alerts.extend(temp_alerts)
        
        # Humidity alerts
        if 'humidity' in current_data:
            humidity_alerts = self._check_humidity_alerts(current_data['humidity'], timestamp)
            alerts.extend(humidity_alerts)
        
        # Data quality alerts
        data_quality_alerts = self._check_data_quality_alerts(current_data, timestamp)
        alerts.extend(data_quality_alerts)
        
        # Process and send alerts
        for alert in alerts:
            self._process_alert(alert)
        
        return alerts

    def _check_pm25_alerts(self, pm25_value: float, timestamp: datetime) -> List[Dict]:
        """Check for PM2.5 related alerts."""
        alerts = []
        thresholds = self.alert_config['alert_thresholds']['pm25']
        
        # Determine alert level
        alert_level = None
        message = None
        
        if pm25_value >= thresholds['critical']:
            alert_level = 'critical'
            message = f"CRITICAL: PM2.5 level extremely high at {pm25_value:.1f} μg/m³"
        elif pm25_value >= thresholds['high']:
            alert_level = 'high'
            message = f"HIGH: PM2.5 level unhealthy at {pm25_value:.1f} μg/m³"
        elif pm25_value >= thresholds['moderate']:
            alert_level = 'medium'
            message = f"MODERATE: PM2.5 level elevated at {pm25_value:.1f} μg/m³"
        
        if alert_level:
            alert = {
                'id': f"pm25_{timestamp.strftime('%Y%m%d_%H%M%S')}",
                'type': 'air_quality',
                'level': alert_level,
                'timestamp': timestamp.isoformat(),
                'metric': 'pm25',
                'value': pm25_value,
                'threshold': thresholds[alert_level],
                'message': message,
                'recommendations': self._get_pm25_recommendations(pm25_value),
                'status': 'active'
            }
            alerts.append(alert)
        
        return alerts

    def _check_temperature_alerts(self, temperature: float, timestamp: datetime) -> List[Dict]:
        """Check for temperature related alerts."""
        alerts = []
        thresholds = self.alert_config['alert_thresholds']['temperature']
        
        alert_level = None
        message = None
        
        if temperature >= thresholds['extreme_high']:
            alert_level = 'high'
            message = f"EXTREME HEAT: Temperature {temperature:.1f}°C exceeds safe limits"
        elif temperature <= thresholds['extreme_low']:
            alert_level = 'high'
            message = f"EXTREME COLD: Temperature {temperature:.1f}°C below safe limits"
        
        if alert_level:
            alert = {
                'id': f"temp_{timestamp.strftime('%Y%m%d_%H%M%S')}",
                'type': 'temperature',
                'level': alert_level,
                'timestamp': timestamp.isoformat(),
                'metric': 'temperature',
                'value': temperature,
                'message': message,
                'recommendations': self._get_temperature_recommendations(temperature),
                'status': 'active'
            }
            alerts.append(alert)
        
        return alerts

    def _check_humidity_alerts(self, humidity: float, timestamp: datetime) -> List[Dict]:
        """Check for humidity related alerts."""
        alerts = []
        thresholds = self.alert_config['alert_thresholds']['humidity']
        
        alert_level = None
        message = None
        
        if humidity >= thresholds['extreme_high']:
            alert_level = 'medium'
            message = f"EXTREME HUMIDITY: Humidity {humidity:.1f}% extremely high"
        elif humidity <= thresholds['extreme_low']:
            alert_level = 'medium'
            message = f"EXTREME DRYNESS: Humidity {humidity:.1f}% extremely low"
        
        if alert_level:
            alert = {
                'id': f"humidity_{timestamp.strftime('%Y%m%d_%H%M%S')}",
                'type': 'humidity',
                'level': alert_level,
                'timestamp': timestamp.isoformat(),
                'metric': 'humidity',
                'value': humidity,
                'message': message,
                'recommendations': self._get_humidity_recommendations(humidity),
                'status': 'active'
            }
            alerts.append(alert)
        
        return alerts

    def _check_data_quality_alerts(self, data: Dict, timestamp: datetime) -> List[Dict]:
        """Check for data quality issues."""
        alerts = []
        
        # Check for missing critical data
        critical_metrics = ['pm25', 'temperature', 'humidity']
        missing_metrics = [metric for metric in critical_metrics if metric not in data or data[metric] is None]
        
        if missing_metrics:
            alert = {
                'id': f"data_missing_{timestamp.strftime('%Y%m%d_%H%M%S')}",
                'type': 'data_quality',
                'level': 'medium',
                'timestamp': timestamp.isoformat(),
                'metric': 'data_completeness',
                'missing_metrics': missing_metrics,
                'message': f"DATA MISSING: Critical metrics unavailable: {', '.join(missing_metrics)}",
                'recommendations': ["Check sensor connectivity", "Verify data collection processes", "Investigate sensor malfunction"],
                'status': 'active'
            }
            alerts.append(alert)
        
        return alerts

    def _get_pm25_recommendations(self, pm25_value: float) -> List[str]:
        """Get recommendations for PM2.5 levels."""
        if pm25_value >= 150:
            return [
                "🚨 Avoid all outdoor activities",
                "Keep windows and doors closed",
                "Use air purifiers if available",
                "Seek medical attention if experiencing symptoms"
            ]
        elif pm25_value >= 55:
            return [
                "⚠️ Limit outdoor activities, especially for sensitive groups",
                "Wear N95 masks when outdoors",
                "Keep windows closed",
                "Monitor health symptoms closely"
            ]
        elif pm25_value >= 35:
            return [
                "ℹ️ Sensitive groups should limit prolonged outdoor activities",
                "Consider indoor exercise alternatives",
                "Monitor air quality regularly"
            ]
        else:
            return ["Monitor daily air quality forecasts"]

    def _get_temperature_recommendations(self, temperature: float) -> List[str]:
        """Get recommendations for extreme temperatures."""
        if temperature >= 40:
            return [
                "🌡️ Extreme heat warning - avoid outdoor activities",
                "Stay hydrated and in air-conditioned spaces",
                "Check on vulnerable community members",
                "Limit physical exertion"
            ]
        elif temperature <= -20:
            return [
                "🥶 Extreme cold warning - limit outdoor exposure",
                "Dress in layers and cover exposed skin",
                "Check heating systems",
                "Watch for signs of hypothermia"
            ]
        else:
            return ["Monitor weather conditions"]

    def _get_humidity_recommendations(self, humidity: float) -> List[str]:
        """Get recommendations for extreme humidity."""
        if humidity >= 95:
            return [
                "💧 Very high humidity - use dehumidifiers if available",
                "Increase ventilation",
                "Monitor for mold growth"
            ]
        elif humidity <= 5:
            return [
                "💨 Very low humidity - use humidifiers if available",
                "Stay hydrated",
                "Monitor for respiratory irritation"
            ]
        else:
            return ["Monitor humidity levels"]

    def _process_alert(self, alert: Dict):
        """Process and send alert through configured channels."""
        alert_id = alert['id']
        
        # Check cooldown period
        if self._is_in_cooldown(alert_id, alert['type']):
            self.logger.info(f"Alert {alert_id} in cooldown period, skipping")
            return
        
        # Add to active alerts
        self.active_alerts[alert_id] = alert
        
        # Send notifications
        if self.alert_config['notification_channels']['file_alerts']['enabled']:
            self._send_file_alert(alert)
        
        if self.alert_config['notification_channels']['email']['enabled']:
            self._send_email_alert(alert)
        
        if self.alert_config['notification_channels']['webhook']['enabled']:
            self._send_webhook_alert(alert)
        
        # Add to history
        self.alert_history.append({
            **alert,
            'processed_at': datetime.now().isoformat()
        })
        
        self.logger.info(f"Alert processed: {alert_id} - {alert['message']}")

    def _is_in_cooldown(self, alert_id: str, alert_type: str) -> bool:
        """Check if alert type is in cooldown period."""
        cooldown_minutes = self.alert_config['alert_rules']['cooldown_minutes']
        cutoff_time = datetime.now() - timedelta(minutes=cooldown_minutes)
        
        # Check recent alerts of same type
        recent_alerts = [
            alert for alert in self.alert_history
            if alert['type'] == alert_type and 
            datetime.fromisoformat(alert['timestamp']) > cutoff_time
        ]
        
        return len(recent_alerts) > 0

    def _send_file_alert(self, alert: Dict):
        """Save alert to file system."""
        try:
            # Update current alerts file
            alerts_file = self.alerts_dir / self.alert_config['notification_channels']['file_alerts']['alert_file']
            current_alerts = {}
            
            if alerts_file.exists():
                try:
                    with open(alerts_file, 'r') as f:
                        current_alerts = json.load(f)
                except Exception:
                    current_alerts = {}
            
            current_alerts[alert['id']] = alert
            
            with open(alerts_file, 'w') as f:
                json.dump(current_alerts, f, indent=2)
            
            # Update history file
            history_file = self.alerts_dir / self.alert_config['notification_channels']['file_alerts']['history_file']
            history = []
            
            if history_file.exists():
                try:
                    with open(history_file, 'r') as f:
                        history = json.load(f)
                except Exception:
                    history = []
            
            history.append({
                **alert,
                'processed_at': datetime.now().isoformat()
            })
            
            # Keep only last 1000 alerts in history
            if len(history) > 1000:
                history = history[-1000:]
            
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)
            
            self.logger.info(f"File alert saved: {alert['id']}")
            
        except Exception as e:
            self.logger.error(f"Error sending file alert: {e}")

    def _send_email_alert(self, alert: Dict):
        """Send alert via email."""
        try:
            if not EMAIL_AVAILABLE:
                self.logger.warning("Email functionality not available")
                return
                
            email_config = self.alert_config['notification_channels']['email']
            
            if not email_config.get('sender_email') or not email_config.get('recipients'):
                self.logger.warning("Email configuration incomplete, skipping email alert")
                return
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = email_config['sender_email']
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = f"Hot Durham Alert: {alert['level'].upper()} - {alert['type'].replace('_', ' ').title()}"
            
            # Email body
            body = f"""
Hot Durham Environmental Monitoring Alert

Alert Level: {alert['level'].upper()}
Type: {alert['type'].replace('_', ' ').title()}
Time: {alert['timestamp']}
Message: {alert['message']}

Recommendations:
{chr(10).join(['• ' + rec for rec in alert.get('recommendations', [])])}

This is an automated alert from the Hot Durham monitoring system.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            
            sender_password = os.getenv("SMTP_SENDER_PASSWORD")
            if sender_password:
                server.login(email_config['sender_email'], sender_password)
            
            server.send_message(msg)
            server.quit()
            
            self.logger.info(f"Email alert sent: {alert['id']}")
            
        except Exception as e:
            self.logger.error(f"Error sending email alert: {e}")

    def _send_webhook_alert(self, alert: Dict):
        """Send alert via webhook."""
        try:
            webhook_config = self.alert_config['notification_channels']['webhook']
            
            if not webhook_config.get('url'):
                return
            
            payload = {
                'alert_id': alert['id'],
                'level': alert['level'],
                'type': alert['type'],
                'timestamp': alert['timestamp'],
                'message': alert['message'],
                'recommendations': alert.get('recommendations', []),
                'source': 'hot_durham_monitoring'
            }
            
            response = requests.post(
                webhook_config['url'],
                json=payload,
                headers=webhook_config.get('headers', {}),
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.info(f"Webhook alert sent: {alert['id']}")
            else:
                self.logger.error(f"Webhook alert failed: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Error sending webhook alert: {e}")

    def get_active_alerts(self) -> Dict:
        """Get all currently active alerts."""
        # Clean up old alerts
        self._cleanup_old_alerts()
        return self.active_alerts

    def _cleanup_old_alerts(self):
        """Remove old alerts that should auto-resolve."""
        auto_resolve_hours = self.alert_config['alert_rules']['auto_resolve_hours']
        cutoff_time = datetime.now() - timedelta(hours=auto_resolve_hours)
        
        alerts_to_remove = []
        for alert_id, alert in self.active_alerts.items():
            alert_time = datetime.fromisoformat(alert['timestamp'])
            if alert_time < cutoff_time:
                alerts_to_remove.append(alert_id)
        
        for alert_id in alerts_to_remove:
            self.active_alerts[alert_id]['status'] = 'auto_resolved'
            self.logger.info(f"Auto-resolved alert: {alert_id}")
            del self.active_alerts[alert_id]

    def generate_alert_summary(self) -> Dict:
        """Generate summary of recent alerts."""
        try:
            # Get alerts from last 24 hours
            last_24h = datetime.now() - timedelta(hours=24)
            recent_alerts = [
                alert for alert in self.alert_history
                if datetime.fromisoformat(alert['timestamp']) > last_24h
            ]
            
            # Count by level and type
            level_counts = {}
            type_counts = {}
            
            for alert in recent_alerts:
                level = alert['level']
                alert_type = alert['type']
                
                level_counts[level] = level_counts.get(level, 0) + 1
                type_counts[alert_type] = type_counts.get(alert_type, 0) + 1
            
            return {
                'summary_period': '24_hours',
                'total_alerts': len(recent_alerts),
                'active_alerts': len(self.active_alerts),
                'alerts_by_level': level_counts,
                'alerts_by_type': type_counts,
                'recent_critical': [
                    alert for alert in recent_alerts[-10:]
                    if alert['level'] in ['critical', 'high']
                ],
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error generating alert summary: {e}")
            return {'error': str(e)}

    def run_enhanced_analysis_with_alerts(self) -> Dict:
        """Run enhanced anomaly detection with real-time alerting."""
        print("🚨 Running enhanced anomaly detection with automated alerting...")
        
        # Run base anomaly analysis
        base_results = self.run_complete_analysis()
        
        # Add alert system results
        enhanced_results = {
            **base_results,
            'alert_system': {
                'active_alerts': self.get_active_alerts(),
                'alert_summary': self.generate_alert_summary(),
                'alert_config_status': {
                    'email_enabled': self.alert_config['notification_channels']['email']['enabled'],
                    'webhook_enabled': self.alert_config['notification_channels']['webhook']['enabled'],
                    'file_alerts_enabled': self.alert_config['notification_channels']['file_alerts']['enabled']
                }
            }
        }
        
        return enhanced_results

def main():
    """Main execution function for standalone testing."""
    print("🚨 Hot Durham Enhanced Anomaly Detection with Alerting")
    print("=" * 60)
    
    # Initialize enhanced system
    detector = EnhancedAnomalyDetector()
    
    # Run complete enhanced analysis
    detector.run_enhanced_analysis_with_alerts()
    
    # Test real-time alert detection
    print("\n🧪 Testing real-time alert detection...")
    test_data = {
        'pm25': 75.5,  # High level
        'temperature': 22.1,
        'humidity': 65.3,
        'timestamp': datetime.now().isoformat()
    }
    
    alerts = detector.detect_real_time_anomalies(test_data)
    
    if alerts:
        print(f"🚨 Generated {len(alerts)} alerts:")
        for alert in alerts:
            print(f"  • {alert['level'].upper()}: {alert['message']}")
    else:
        print("✅ No alerts generated for test data")
    
    # Show alert summary
    summary = detector.generate_alert_summary()
    print(f"\n📊 Alert Summary (24h): {summary['total_alerts']} total, {summary['active_alerts']} active")

if __name__ == "__main__":
    main()
