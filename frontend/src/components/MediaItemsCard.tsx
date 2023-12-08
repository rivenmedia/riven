import React, { useState } from 'react';
import { Card, CardContent, CardActions, Button, Typography, Collapse } from '@mui/material';
import { MediaItemCardProps } from '../types/Types';
import styles from './MediaItems.module.css';

function MediaItemsCard({ title, items }: MediaItemCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <Card className={styles.card}>
      <CardContent className={styles.cardHeader}>
        <Typography variant="h5" component="div" className={styles.title}>
          {title}
        </Typography>
        <Button size="small" onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Show'}
        </Button>
      </CardContent>
      <Collapse in={open}>
        <CardContent>
          {items.map(item => (
            <Typography key={item.guid} paragraph className={styles.item}>
              {item.title} ({item.type}, {item.year})
            </Typography>
          ))}
        </CardContent>
      </Collapse>
      <CardContent className={styles.cardFooter}>
        <Typography variant="body2">
          Media items: {items.length}
        </Typography>
      </CardContent>
    </Card>
);
}

export default MediaItemsCard;
