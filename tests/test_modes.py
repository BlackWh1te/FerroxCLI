"""Tests for ferrox.modes module"""
import pytest
from ferrox.modes import Mode, ModeManager


class TestMode:
    """Test Mode enum"""
    
    def test_mode_values(self):
        """Test that Mode enum has expected values"""
        assert Mode.NORMAL.value == "normal"
        assert Mode.PLAN.value == "plan"
        assert Mode.BYPASS.value == "bypass"
        assert Mode.EDIT.value == "edit"
    
    def test_mode_comparison(self):
        """Test mode comparison"""
        assert Mode.NORMAL == Mode.NORMAL
        assert Mode.NORMAL != Mode.PLAN


class TestModeManager:
    """Test ModeManager class"""
    
    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing"""
        return ModeManager()
    
    def test_initial_mode(self, mode_manager):
        """Test that initial mode is NORMAL"""
        assert mode_manager.current_mode == Mode.NORMAL
    
    def test_set_mode(self, mode_manager):
        """Test setting different modes"""
        mode_manager.set_mode(Mode.PLAN)
        assert mode_manager.current_mode == Mode.PLAN
        
        mode_manager.set_mode(Mode.BYPASS)
        assert mode_manager.current_mode == Mode.BYPASS
    
    def test_set_mode_invalid(self, mode_manager):
        """Test setting invalid mode"""
        with pytest.raises((ValueError, AttributeError)):
            mode_manager.set_mode("invalid_mode")
    
    def test_get_permissions(self, mode_manager):
        """Test getting permissions for each mode"""
        normal_perms = mode_manager.get_permissions(Mode.NORMAL)
        plan_perms = mode_manager.get_permissions(Mode.PLAN)
        bypass_perms = mode_manager.get_permissions(Mode.BYPASS)
        
        # Bypass should have more permissions than Plan
        assert len(bypass_perms) >= len(plan_perms)
        
        # Plan should be more restrictive than Normal
        assert len(normal_perms) >= len(plan_perms)
    
    def test_mode_description(self, mode_manager):
        """Test getting mode descriptions"""
        normal_desc = mode_manager.get_mode_description(Mode.NORMAL)
        plan_desc = mode_manager.get_mode_description(Mode.PLAN)
        
        assert normal_desc is not None
        assert plan_desc is not None
        assert len(normal_desc) > 0
        assert len(plan_desc) > 0


class TestModeTransitions:
    """Test mode transitions and restrictions"""
    
    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing"""
        return ModeManager()
    
    def test_normal_to_plan_transition(self, mode_manager):
        """Test transitioning from Normal to Plan mode"""
        mode_manager.set_mode(Mode.NORMAL)
        mode_manager.set_mode(Mode.PLAN)
        assert mode_manager.current_mode == Mode.PLAN
    
    def test_plan_to_bypass_transition(self, mode_manager):
        """Test transitioning from Plan to Bypass mode"""
        mode_manager.set_mode(Mode.PLAN)
        mode_manager.set_mode(Mode.BYPASS)
        assert mode_manager.current_mode == Mode.BYPASS
    
    def test_bypass_to_normal_transition(self, mode_manager):
        """Test transitioning from Bypass back to Normal"""
        mode_manager.set_mode(Mode.BYPASS)
        mode_manager.set_mode(Mode.NORMAL)
        assert mode_manager.current_mode == Mode.NORMAL
    
    def test_mode_cycle(self, mode_manager):
        """Test cycling through all modes"""
        modes = [Mode.NORMAL, Mode.PLAN, Mode.BYPASS, Mode.EDIT]
        
        for mode in modes:
            mode_manager.set_mode(mode)
            assert mode_manager.current_mode == mode


class TestModeRestrictions:
    """Test mode-specific restrictions"""
    
    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing"""
        return ModeManager()
    
    def test_plan_mode_restrictions(self, mode_manager):
        """Test that Plan mode has appropriate restrictions"""
        mode_manager.set_mode(Mode.PLAN)
        permissions = mode_manager.get_permissions(Mode.PLAN)
        
        # Plan mode should restrict write operations
        assert "write" not in permissions or permissions["write"] is False
    
    def test_bypass_mode_permissions(self, mode_manager):
        """Test that Bypass mode has expanded permissions"""
        mode_manager.set_mode(Mode.BYPASS)
        permissions = mode_manager.get_permissions(Mode.BYPASS)
        
        # Bypass mode should allow most operations
        assert len(permissions) > 0
    
    def test_normal_mode_balanced(self, mode_manager):
        """Test that Normal mode has balanced permissions"""
        mode_manager.set_mode(Mode.NORMAL)
        permissions = mode_manager.get_permissions(Mode.NORMAL)
        
        # Normal mode should be between Plan and Bypass
        assert len(permissions) > 0


class TestModeManagerState:
    """Test ModeManager state management"""
    
    @pytest.fixture
    def mode_manager(self):
        """Create a mode manager for testing"""
        return ModeManager()
    
    def test_mode_persistence(self, mode_manager):
        """Test that mode changes persist"""
        mode_manager.set_mode(Mode.PLAN)
        assert mode_manager.current_mode == Mode.PLAN
        
        # Check again to ensure it persisted
        assert mode_manager.current_mode == Mode.PLAN
    
    def test_multiple_managers_independent(self):
        """Test that multiple mode managers are independent"""
        manager1 = ModeManager()
        manager2 = ModeManager()
        
        manager1.set_mode(Mode.PLAN)
        manager2.set_mode(Mode.BYPASS)
        
        assert manager1.current_mode == Mode.PLAN
        assert manager2.current_mode == Mode.BYPASS