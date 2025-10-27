import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SubscriptionService:
    def __init__(self, database, vpn_manager):
        self.db = database
        self.vpn_manager = vpn_manager
        
    def create_subscription(self, user_id: int, duration_days: int = 30, 
                          subscription_name: str = None, data_limit: int = 0) -> Dict[str, Any]:
        """
        Создать новую подписку
        
        Args:
            user_id: ID пользователя в Telegram
            duration_days: Длительность подписки в днях
            subscription_name: Название подписки (опционально)
            data_limit: Лимит трафика в байтах (0 = безлимит)
            
        Returns:
            Dict с информацией о созданной подписке
        """
        try:
            # Генерируем уникальное имя пользователя для VPN
            vpn_username = self._generate_vpn_username(user_id)
            
            # Вычисляем дату истечения
            expire_date = datetime.now() + timedelta(days=duration_days)
            expire_timestamp = int(expire_date.timestamp())
            
            # Создаем пользователя в Marzban
            vpn_user_data = self.vpn_manager.create_user(
                username=vpn_username,
                expireAt=expire_timestamp,
                data_limit=data_limit,
                status='active'
            )
            
            # Сохраняем в базу данных
            if not subscription_name:
                subscription_name = f"VPN {datetime.now().strftime('%d.%m.%Y')}"
            
            subscription_id = self.db.add_subscription(
                user_id=user_id,
                vpn_username=vpn_username,
                subscription_name=subscription_name,
                expires_at=expire_date
            )
            
            # Получаем конфигурацию
            config_data = self.vpn_manager.get_user_config(vpn_username)
            
            result = {
                'subscription_id': subscription_id,
                'vpn_username': vpn_username,
                'subscription_name': subscription_name,
                'expires_at': expire_date,
                'config': config_data.get('config', ''),
                'subscription_url': config_data.get('subscription_url', ''),
                'link': config_data.get('link', ''),
                'success': True
            }
            
            logger.info(f"Successfully created subscription for user {user_id}: {vpn_username}")
            return result
            
        except Exception as e:
            logger.error(f"Error creating subscription for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def extend_subscription(self, vpn_username: str, duration_days: int = 30) -> Dict[str, Any]:
        """
        Продлить существующую подписку
        
        Args:
            vpn_username: Имя пользователя VPN
            duration_days: На сколько дней продлить
            
        Returns:
            Dict с результатом операции
        """
        try:
            # Получаем информацию о подписке
            subscription = self.db.get_subscription_by_vpn_username(vpn_username)
            if not subscription:
                return {
                    'success': False,
                    'error': 'Subscription not found'
                }
            
            # Получаем текущую информацию о пользователе в Marzban
            try:
                current_user = self.vpn_manager.get_user_config(vpn_username)
            except:
                # Если пользователь не найден в Marzban, пересоздаем его
                expire_date = datetime.now() + timedelta(days=duration_days)
                expire_timestamp = int(expire_date.timestamp())
                
                self.vpn_manager.create_user(
                    username=vpn_username,
                    expireAt=expire_timestamp,
                    status='active'
                )
                
                return {
                    'success': True,
                    'message': f'Subscription recreated and extended by {duration_days} days',
                    'expires_at': expire_date
                }
            
            # Вычисляем новую дату истечения
            current_expires = subscription[5]  # expires_at field
            if current_expires:
                current_expire_date = datetime.fromisoformat(current_expires.replace('Z', '+00:00'))
                if current_expire_date > datetime.now():
                    # Если подписка еще активна, продлеваем от текущей даты истечения
                    new_expire_date = current_expire_date + timedelta(days=duration_days)
                else:
                    # Если подписка истекла, продлеваем от текущего момента
                    new_expire_date = datetime.now() + timedelta(days=duration_days)
            else:
                new_expire_date = datetime.now() + timedelta(days=duration_days)
            
            new_expire_timestamp = int(new_expire_date.timestamp())
            
            # Обновляем пользователя в Marzban (пересоздаем с новой датой)
            try:
                self.vpn_manager.delete_user(vpn_username)
            except:
                pass  # Игнорируем ошибки удаления
            
            self.vpn_manager.create_user(
                username=vpn_username,
                expireAt=new_expire_timestamp,
                status='active'
            )
            
            # Обновляем в базе данных
            import sqlite3
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions 
                    SET expires_at = ?
                    WHERE vpn_username = ? AND is_active = 1
                ''', (new_expire_date, vpn_username))
                conn.commit()
            
            logger.info(f"Successfully extended subscription {vpn_username} by {duration_days} days")
            return {
                'success': True,
                'message': f'Subscription extended by {duration_days} days',
                'expires_at': new_expire_date
            }
            
        except Exception as e:
            logger.error(f"Error extending subscription {vpn_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_subscription(self, vpn_username: str) -> Dict[str, Any]:
        """
        Удалить подписку
        
        Args:
            vpn_username: Имя пользователя VPN
            
        Returns:
            Dict с результатом операции
        """
        try:
            # Удаляем из Marzban
            try:
                self.vpn_manager.delete_user(vpn_username)
            except Exception as e:
                logger.warning(f"Error deleting user from Marzban: {e}")
                # Продолжаем выполнение даже если не удалось удалить из Marzban
            
            # Деактивируем в базе данных
            success = self.db.deactivate_subscription(vpn_username)
            
            if success:
                logger.info(f"Successfully deleted subscription {vpn_username}")
                return {
                    'success': True,
                    'message': 'Subscription deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Subscription not found in database'
                }
                
        except Exception as e:
            logger.error(f"Error deleting subscription {vpn_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_subscriptions(self, user_id: int) -> list:
        """
        Получить все подписки пользователя
        
        Args:
            user_id: ID пользователя в Telegram
            
        Returns:
            List подписок пользователя
        """
        try:
            subscriptions = self.db.get_user_subscriptions(user_id)
            result = []
            
            for sub in subscriptions:
                sub_data = {
                    'id': sub[0],
                    'user_id': sub[1],
                    'vpn_username': sub[2],
                    'subscription_name': sub[3],
                    'created_at': sub[4],
                    'expires_at': sub[5],
                    'is_active': sub[6]
                }
                
                # Проверяем статус в Marzban
                try:
                    config = self.vpn_manager.get_user_config(sub[2])
                    sub_data['config'] = config.get('config', '')
                    sub_data['subscription_url'] = config.get('subscription_url', '')
                    sub_data['marzban_status'] = 'active'
                except Exception as e:
                    logger.warning(f"Could not get config for {sub[2]}: {e}")
                    sub_data['marzban_status'] = 'inactive'
                
                result.append(sub_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting subscriptions for user {user_id}: {e}")
            return []
    
    def rename_subscription(self, vpn_username: str, new_name: str) -> Dict[str, Any]:
        """
        Переименовать подписку
        
        Args:
            vpn_username: Имя пользователя VPN
            new_name: Новое название
            
        Returns:
            Dict с результатом операции
        """
        try:
            success = self.db.update_subscription_name(vpn_username, new_name)
            
            if success:
                logger.info(f"Successfully renamed subscription {vpn_username} to '{new_name}'")
                return {
                    'success': True,
                    'message': f'Subscription renamed to "{new_name}"'
                }
            else:
                return {
                    'success': False,
                    'error': 'Subscription not found'
                }
                
        except Exception as e:
            logger.error(f"Error renaming subscription {vpn_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_subscription_config(self, vpn_username: str) -> Dict[str, Any]:
        """
        Получить конфигурацию подписки
        
        Args:
            vpn_username: Имя пользователя VPN
            
        Returns:
            Dict с конфигурацией
        """
        try:
            config = self.vpn_manager.get_user_config(vpn_username)
            return {
                'success': True,
                'config': config.get('config', ''),
                'subscription_url': config.get('subscription_url', ''),
                'link': config.get('link', '')
            }
            
        except Exception as e:
            logger.error(f"Error getting config for {vpn_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_vpn_username(self, user_id: int) -> str:
        """
        Генерировать уникальное имя пользователя для VPN
        
        Args:
            user_id: ID пользователя в Telegram
            
        Returns:
            Уникальное имя пользователя
        """
        # Используем комбинацию user_id и timestamp для уникальности
        timestamp = int(datetime.now().timestamp())
        return f"user_{user_id}_{timestamp}"
    
    def check_subscription_status(self, vpn_username: str) -> Dict[str, Any]:
        """
        Проверить статус подписки
        
        Args:
            vpn_username: Имя пользователя VPN
            
        Returns:
            Dict со статусом подписки
        """
        try:
            # Проверяем в базе данных
            subscription = self.db.get_subscription_by_vpn_username(vpn_username)
            if not subscription:
                return {
                    'success': False,
                    'error': 'Subscription not found in database'
                }
            
            # Проверяем в Marzban
            try:
                config = self.vpn_manager.get_user_config(vpn_username)
                marzban_status = 'active'
            except:
                marzban_status = 'inactive'
            
            # Проверяем дату истечения
            expires_at = subscription[5]
            is_expired = False
            if expires_at:
                expire_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                is_expired = expire_date < datetime.now()
            
            return {
                'success': True,
                'subscription_name': subscription[3],
                'created_at': subscription[4],
                'expires_at': expires_at,
                'is_expired': is_expired,
                'marzban_status': marzban_status,
                'is_active': bool(subscription[6])
            }
            
        except Exception as e:
            logger.error(f"Error checking status for {vpn_username}: {e}")
            return {
                'success': False,
                'error': str(e)
            }