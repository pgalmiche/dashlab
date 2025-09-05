from importlib import reload
from unittest.mock import patch



def test_main_does_not_run_in_non_development():
    """
    Test that main.py does NOT call app.run when env is not 'development'.
    """
    with patch('app.main.settings') as mock_settings:
        mock_settings.env = 'production'
        mock_settings.debug = True

        with patch('app.main.app.run') as mock_run:
            import app.main as main_module

            reload(main_module)

            mock_run.assert_not_called()
