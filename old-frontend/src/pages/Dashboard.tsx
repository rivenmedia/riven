import * as React from 'react';
import '../App.css';
import { styled, createTheme, ThemeProvider, useTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import MuiDrawer from '@mui/material/Drawer';
import Box from '@mui/material/Box';
import MuiAppBar, { AppBarProps as MuiAppBarProps } from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import List from '@mui/material/List';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Container from '@mui/material/Container';
import Link from '@mui/material/Link';
import MenuIcon from '@mui/icons-material/Menu';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import LightMode from '@mui/icons-material/LightMode';
import DarkMode from '@mui/icons-material/DarkMode'
import { mainListItems, secondaryListItems } from '../components/listItems';
import Paper from '@mui/material/Paper';
import { ListItemButton } from '@mui/material';

function Copyright(props: any) {
  return (
    <Typography variant="body2" color="text.secondary" align="center" {...props}>
      {'Powered by '}
      <Link color="inherit" target="_blank" href="https://mui.com/">
        MUI
      </Link>
      {'.'}
    </Typography>
  );
}

const drawerWidth: number = 240;

interface AppBarProps extends MuiAppBarProps {
  open?: boolean;
}

const AppBar = styled(MuiAppBar, {
  shouldForwardProp: (prop) => prop !== 'open',
})<AppBarProps>(({ theme }) => ({
  zIndex: theme.zIndex.drawer + 1,
  transition: theme.transitions.create(['width', 'margin'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  borderRadius: '10px',
  position: 'relative'
}));

const Drawer = styled(MuiDrawer, { shouldForwardProp: (prop) => prop !== 'open' })(
  ({ theme, open }) => ({
    '& .MuiDrawer-paper': {
      position: 'relative',
      whiteSpace: '',
      borderRadius: '10px',
      width: drawerWidth,
      transition: theme.transitions.create('width', {
        easing: theme.transitions.easing.sharp,
        duration: theme.transitions.duration.enteringScreen,
      }),
      boxSizing: 'border-box',
      ...(!open && {
        overflowX: 'hidden',
        transition: theme.transitions.create('width', {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.leavingScreen,
        }),
        width: theme.spacing(7),
        [theme.breakpoints.up('sm')]: {
          width: theme.spacing(9),
        },
      }),
    },
  }),
);

const ThemeToggleButton: React.FC<{ toggleTheme: () => void }> = ({ toggleTheme }) => {
  const theme = useTheme();

  return (
    <IconButton onClick={toggleTheme}>
      {theme.palette.mode === 'light'? <DarkMode /> : <LightMode />}
    </IconButton>
  )
}

interface MenuToggleButtonProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  [key: string]: any;
}

const MenuToggleButton: React.FC<MenuToggleButtonProps> = ({ open, setOpen, ...props }) => {

  return (
    <ListItemButton onClick={() => setOpen(!open)} {...props}>
      {open ? <ChevronLeftIcon /> : <MenuIcon />}
    </ListItemButton>
    // <IconButton onClick={() => setOpen(!open)} {...props}>
    //   {open ? <ChevronLeftIcon /> : <MenuIcon />}
    // </IconButton>
  )
}

interface DashboardProps {
  PageComponent: React.ComponentType;
}

const font = "'Poppins', sans-serif"
// TODO remove, this demo shouldn't need to reset the theme.
const darkTheme = createTheme({ palette: { mode: 'dark' }, typography: {fontFamily: font}});
const lightTheme = createTheme({ palette: { mode: 'light' }, typography: {fontFamily: font}});

const Dashboard: React.FC<DashboardProps> = ( {PageComponent}) =>{

  const [open, setOpen] = React.useState(true);

  const savedTheme = localStorage.getItem('theme');
  const defaultTheme = savedTheme === 'dark' ? darkTheme : lightTheme;
  const [theme, setTheme] = React.useState(defaultTheme);

  const toggleTheme = () => {
      let newTheme = theme === lightTheme ? darkTheme : lightTheme;
      setTheme(newTheme);
      localStorage.setItem('theme', newTheme === lightTheme ? 'light' : 'dark');
  };

  return (
    <ThemeProvider theme={theme}>
      <Box component="main"
          sx={{
            backgroundColor: (theme) =>
              theme.palette.mode === 'light'
                ? theme.palette.grey[100]
                : theme.palette.grey[900],
            flexGrow: 1,
            height: '100vh',
            width: '100%',
            overflow: 'auto',
            alignItems: 'center',
            pt: ".5%",
            pl: '1%',
            pr: '1%',
            pb: '.5%',
          }}>
        <CssBaseline />
        <Box component="header" width = "100%" height = '64px'>
            <AppBar open={open}>
              <Toolbar>
                <Typography
                  component="h1"
                  variant="h6"
                  color="inherit"
                  noWrap
                  sx={{ flexGrow: 1 }}
                >
                  Plex Debrid
                </Typography>
                <ThemeToggleButton toggleTheme={toggleTheme} />
              </Toolbar>
            </AppBar>
        </Box>
        <Box sx={{ display: 'flex', width: '100%', pt: '1%', height: '100%'}}>
          <Box component="nav" width={drawerWidth}>
            <Drawer variant="permanent" open={open}>
              <List component="nav">
                <MenuToggleButton
                    open={open} setOpen={setOpen}
                  />
                  <Divider />
                  {mainListItems}
              </List>
            </Drawer>
          </Box>
          <Box width='95%'>
            <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }} >
              <Paper elevation={3} sx={{ p: 2 }}>
                <PageComponent />
              </Paper>
              <Copyright sx={{ pt: 4 }} />
            </Container>
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default Dashboard;
